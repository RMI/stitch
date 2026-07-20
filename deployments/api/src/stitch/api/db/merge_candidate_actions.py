from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from stitch.api.auth import CurrentUser
from stitch.api.coalesce import coalesce_og_field_resource
from stitch.api.db.errors import (
    InvalidActionError,
    ResourceIntegrityError,
    ResourceNotFoundError,
)
from stitch.api.entities import (
    FieldComparisonView,
    MergeCandidateCreateRequest,
    MergeCandidateDetailView,
    MergeCandidateReviewRequest,
    MergeCandidateStatus,
    MergeCandidateView,
    OGFieldMergePreviewView,
)
from stitch.ogsi.model import (
    OGFieldDetailView,
    OGFieldSource,
    OGFieldSourceValueView,
)
from stitch.ogsi.model.og_field import OilGasFieldBase
from stitch.ogsi.model.types import OGSISrcKey

from .model import (
    MergeCandidateItemModel,
    MergeCandidateModel,
    MembershipModel,
    MembershipStatus,
    OGFieldSourcePriority,
    OilGasFieldSourceModel,
    ResourceModel,
)
from .og_field_resource_actions import apply_resource_merge
from .utils import coalesce_resources, resource_to_detail_view


def _normalize_resource_ids(resource_ids: Sequence[int]) -> list[int]:
    unique_ids = list(dict.fromkeys(resource_ids))
    if len(unique_ids) < 2:
        raise InvalidActionError(
            f"Merging only possible between multiple ids: received: {unique_ids}"
        )
    return unique_ids


async def _load_mergeable_resources(
    session: AsyncSession, resource_ids: Sequence[int]
) -> list[ResourceModel]:
    unique_ids = _normalize_resource_ids(resource_ids)
    stmt = select(ResourceModel).where(ResourceModel.id.in_(unique_ids))
    results = (await session.scalars(stmt)).all()

    missing_ids = set(unique_ids).difference({r.id for r in results})
    if missing_ids:
        msg = (
            f"Resources not found for ids: [{','.join(map(str, sorted(missing_ids)))}]"
        )
        raise ResourceNotFoundError(msg)

    repointed = [r for r in results if r.repointed_id is not None]
    if repointed:
        reprs = map(repr, repointed)
        msg = f"Repointed: [{','.join(reprs)}]"
        raise ResourceIntegrityError(
            f"Cannot merge any resource that has already been merged. {msg}"
        )

    return results


def _fingerprint(resource_ids: Sequence[int]) -> str:
    return ":".join(map(str, sorted(set(resource_ids))))


def _candidate_to_view(model: MergeCandidateModel) -> MergeCandidateView:
    return MergeCandidateView(
        id=model.id,
        resource_ids=[
            item.resource_id for item in sorted(model.items, key=lambda i: i.position)
        ],
        status=model.status,
        review_notes=model.review_notes,
        merged_resource_id=model.merged_resource_id,
        created=model.created,
        updated=model.updated,
        created_by_id=model.created_by_id,
        last_updated_by_id=model.last_updated_by_id,
        reviewed_at=model.reviewed_at,
        reviewed_by_id=model.reviewed_by_id,
    )


def _comparison_status(
    base_value: Any,
    winner: Any,
    values: Sequence[OGFieldSourceValueView],
) -> str:
    """Classify a field's merge outcome against the baseline resource value.

    ``base_value`` is ``resources[0]``'s coalesced value; ``winner`` is the
    highest-priority source value (``values[0]``). See ``FieldComparisonView``.
    """
    if base_value is None:
        return "new" if winner is not None else "unchanged"
    if winner != base_value:
        return "mismatch"
    if all(entry.value == base_value for entry in values):
        return "match"
    return "unchanged"


def _build_comparison(
    baseline: OGFieldDetailView | None,
    sources_with_priority: Sequence[tuple[OGFieldSource, int]],
) -> list[FieldComparisonView]:
    """Per-field comparison across every contributing source in the candidate.

    For each ``OilGasFieldBase`` field, list every source that carries a value
    (winner-first by effective priority), then classify the merge outcome against
    the baseline (``resources[0]``). See ``FieldComparisonView`` for the status
    semantics. ``priority`` is the default source order, since a merge resets the
    merged resource to default ordering.

    The winner picked here is a best guess at the persisted merge result,
    coalesced in Python; it is superseded once coalescing moves into the DB.
    """
    comparison: list[FieldComparisonView] = []
    for field_name in OilGasFieldBase.model_fields:
        values: list[OGFieldSourceValueView] = []
        for source, priority in sources_with_priority:
            if source.id is None:
                continue
            value = getattr(source, field_name, None)
            if value is None or value == "":
                continue
            values.append(
                OGFieldSourceValueView(
                    source=source.source,
                    id=source.id,
                    value=value,
                    priority=priority,
                )
            )
        values.sort(key=lambda entry: (entry.priority, entry.id))
        winner = values[0].value if values else None
        base_value = (
            getattr(baseline.data, field_name, None) if baseline is not None else None
        )
        comparison.append(
            FieldComparisonView(
                field=field_name,
                status=_comparison_status(base_value, winner, values),
                values=values,
            )
        )
    return comparison


async def _default_source_priority(session: AsyncSession) -> dict[str, int]:
    """Global default source ordering (``source`` key -> priority, lower wins).

    A merge resets the merged resource to this default order, so the comparison
    ranks sources by it rather than by any per-resource override.
    """
    rows = await session.execute(
        select(OGFieldSourcePriority.source, OGFieldSourcePriority.priority)
    )
    return {source: priority for source, priority in rows.all()}


def _candidate_to_detail_view(
    model: MergeCandidateModel,
    resources: Sequence[OGFieldDetailView],
    compare: Sequence[FieldComparisonView],
) -> MergeCandidateDetailView:
    return MergeCandidateDetailView(
        id=model.id,
        resource_ids=[
            item.resource_id for item in sorted(model.items, key=lambda i: i.position)
        ],
        status=model.status,
        review_notes=model.review_notes,
        merged_resource_id=model.merged_resource_id,
        created=model.created,
        updated=model.updated,
        created_by_id=model.created_by_id,
        last_updated_by_id=model.last_updated_by_id,
        reviewed_at=model.reviewed_at,
        reviewed_by_id=model.reviewed_by_id,
        resources=list(resources),
        compare=list(compare),
    )


async def _load_candidate_model(
    session: AsyncSession, candidate_id: int
) -> MergeCandidateModel:
    stmt = (
        select(MergeCandidateModel)
        .options(selectinload(MergeCandidateModel.items))
        .where(MergeCandidateModel.id == candidate_id)
    )
    model = await session.scalar(stmt)
    if model is None:
        raise ResourceNotFoundError(
            f"No merge candidate found for id = {candidate_id}."
        )
    return model


async def list_merge_candidates(session: AsyncSession) -> list[MergeCandidateView]:
    stmt = (
        select(MergeCandidateModel)
        .options(selectinload(MergeCandidateModel.items))
        .order_by(MergeCandidateModel.created.desc())
    )
    candidates = (await session.scalars(stmt)).all()
    return [_candidate_to_view(candidate) for candidate in candidates]


async def get_merge_candidate(
    session: AsyncSession,
    candidate_id: int,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> MergeCandidateDetailView:
    candidate = await _load_candidate_model(session, candidate_id)

    resource_ids = [
        item.resource_id for item in sorted(candidate.items, key=lambda i: i.position)
    ]

    # Computed live: repointed (post-merge) resources coalesce to a null-shell
    # view here, so an APPROVED candidate's `resources`/`compare` reflect the
    # emptied originals. Freezing a snapshot at approve/deny time is deferred.
    by_id = await coalesce_resources(session, resource_ids, licensed_sources)
    resources = [resource_to_detail_view(by_id[rid]) for rid in resource_ids]

    # Compare every contributing source against the baseline (resources[0]),
    # ranked by the default source order the merged resource will use.
    default_priority = await _default_source_priority(session)
    fallback_priority = max(default_priority.values(), default=0) + 1
    sources_with_priority = [
        (source, default_priority.get(source.source, fallback_priority))
        for rid in resource_ids
        for source in by_id[rid].source_data
    ]
    baseline = resources[0] if resources else None
    compare = _build_comparison(baseline, sources_with_priority)

    return _candidate_to_detail_view(candidate, resources, compare)


async def create_merge_candidate(
    session: AsyncSession,
    user: CurrentUser,
    request: MergeCandidateCreateRequest,
) -> MergeCandidateView:
    resource_ids = _normalize_resource_ids(request.resource_ids)
    await _load_mergeable_resources(session, resource_ids)

    fingerprint = _fingerprint(resource_ids)
    existing = await session.scalar(
        select(MergeCandidateModel)
        .options(selectinload(MergeCandidateModel.items))
        .where(MergeCandidateModel.fingerprint == fingerprint)
    )
    if existing is not None:
        if existing.status == MergeCandidateStatus.PENDING:
            raise InvalidActionError(
                f"A pending merge candidate already exists for resources {resource_ids}."
            )
        if existing.status == MergeCandidateStatus.DENIED:
            raise InvalidActionError(
                f"A denied merge candidate already exists for resources {resource_ids}."
            )
        raise InvalidActionError(
            f"An approved merge candidate already exists for resources {resource_ids}."
        )

    candidate = MergeCandidateModel.create(created_by=user, fingerprint=fingerprint)
    session.add(candidate)
    await session.flush()

    session.add_all(
        [
            MergeCandidateItemModel(
                merge_candidate_id=candidate.id,
                resource_id=resource_id,
                position=position,
            )
            for position, resource_id in enumerate(resource_ids)
        ]
    )
    await session.flush()
    await session.refresh(candidate, ["items"])
    return _candidate_to_view(candidate)


async def approve_merge_candidate(
    session: AsyncSession,
    user: CurrentUser,
    candidate_id: int,
    request: MergeCandidateReviewRequest | None = None,
) -> MergeCandidateView:
    candidate = await _load_candidate_model(session, candidate_id)
    if candidate.status != MergeCandidateStatus.PENDING:
        raise InvalidActionError(
            f"Merge candidate {candidate_id} is not pending; current status={candidate.status}."
        )

    resource_ids = [
        item.resource_id for item in sorted(candidate.items, key=lambda i: i.position)
    ]
    await _load_mergeable_resources(session, resource_ids)
    merged_resource = await apply_resource_merge(
        session=session,
        user=user,
        resource_ids=resource_ids,
    )

    candidate.status = MergeCandidateStatus.APPROVED
    candidate.review_notes = request.review_notes if request else None
    candidate.reviewed_at = datetime.now(timezone.utc)
    candidate.reviewed_by_id = user.id
    candidate.last_updated_by_id = user.id
    candidate.merged_resource_id = merged_resource.id
    await session.flush()

    candidate = await _load_candidate_model(session, candidate_id)
    return _candidate_to_view(candidate)


async def deny_merge_candidate(
    session: AsyncSession,
    user: CurrentUser,
    candidate_id: int,
    request: MergeCandidateReviewRequest | None = None,
) -> MergeCandidateView:
    candidate = await _load_candidate_model(session, candidate_id)
    if candidate.status != MergeCandidateStatus.PENDING:
        raise InvalidActionError(
            f"Merge candidate {candidate_id} is not pending; current status={candidate.status}."
        )

    candidate.status = MergeCandidateStatus.DENIED
    candidate.review_notes = request.review_notes if request else None
    candidate.reviewed_at = datetime.now(timezone.utc)
    candidate.reviewed_by_id = user.id
    candidate.last_updated_by_id = user.id
    await session.flush()
    candidate = await _load_candidate_model(session, candidate_id)
    return _candidate_to_view(candidate)


async def preview_merge_candidate(
    session: AsyncSession,
    candidate_id: int,
) -> OGFieldMergePreviewView:
    candidate = await _load_candidate_model(session, candidate_id)

    resource_ids = [
        item.resource_id for item in sorted(candidate.items, key=lambda i: i.position)
    ]

    await _load_mergeable_resources(session, resource_ids)

    stmt = (
        select(OilGasFieldSourceModel)
        .join(
            MembershipModel,
            MembershipModel.source_pk == OilGasFieldSourceModel.id,
        )
        .where(MembershipModel.resource_id.in_(resource_ids))
        .where(MembershipModel.status == MembershipStatus.ACTIVE)
    )
    source_models = (await session.scalars(stmt)).all()

    priorities = (
        await session.scalars(
            select(OGFieldSourcePriority.source).order_by(
                OGFieldSourcePriority.priority
            )
        )
    ).all()

    source_entities = [src.as_entity() for src in source_models]
    merged_data, raw_provenance = coalesce_og_field_resource(
        source_entities,
        priorities,
    )

    provenance: dict[str, OGSISrcKey | None] = {
        key: (None if value is None else value[1])
        for key, value in raw_provenance.items()
    }

    data = OilGasFieldBase(
        **{
            field_name: getattr(merged_data, field_name, None)
            for field_name in OilGasFieldBase.model_fields
        }
    )

    return OGFieldMergePreviewView(
        resource_ids=resource_ids,
        data=data,
        provenance=provenance,
    )
