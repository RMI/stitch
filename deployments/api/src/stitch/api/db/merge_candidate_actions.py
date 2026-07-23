from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from stitch.api.auth import CurrentUser
from stitch.api.db.errors import (
    InvalidActionError,
    ResourceIntegrityError,
    ResourceNotFoundError,
)
from stitch.api.entities import (
    ComparisonValueView,
    FieldComparisonView,
    MergeCandidateCreateRequest,
    MergeCandidateDetailView,
    MergeCandidateReviewRequest,
    MergeCandidateStatus,
    MergeCandidateView,
)
from stitch.ogsi.model import OGFieldSource
from stitch.ogsi.model.og_field import OilGasFieldBase
from stitch.ogsi.model.types import OGSISrcKey

from .model import (
    MergeCandidateItemModel,
    MergeCandidateModel,
    OGFieldSourcePriority,
    ResourceModel,
)
from .og_field_resource_actions import apply_resource_merge
from .utils import coalesce_resources_with_sources


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


def _comparison_status(resource_values: Sequence[Any]) -> str:
    """``match`` if every resource resolves to the same value, else ``different``.

    Compares each resource's coalesced value for a field. A value present on one
    resource and null on another counts as ``different``; all-null counts as
    ``match``. See ``FieldComparisonView``.
    """
    first = resource_values[0] if resource_values else None
    return "match" if all(value == first for value in resource_values) else "different"


def _build_comparison(
    resource_views: Sequence[OilGasFieldBase],
    sources_with_priority: Sequence[tuple[int, OGFieldSource, int]],
) -> list[FieldComparisonView]:
    """Per-field comparison across the candidate's resources.

    For each ``OilGasFieldBase`` field, ``status`` compares the resources'
    coalesced values (``resource_views``); ``values`` lists every source that
    carries a value (winner-first by priority) tagged with the resource it is
    attached to. See ``FieldComparisonView`` for the status semantics.

    Values are a best guess at the persisted merge result: a merge drops any
    per-resource overrides, so the merged resource can resolve to a value that
    differs from any single parent's current winner.
    """
    comparison: list[FieldComparisonView] = []
    for field_name in OilGasFieldBase.model_fields:
        values: list[ComparisonValueView] = []
        for resource_id, source, priority in sources_with_priority:
            if source.id is None:
                continue
            value = getattr(source, field_name, None)
            # None means "unset". Empty strings can't be persisted (write-path
            # skip + DB CHECK), so a null check alone captures every real value.
            if value is None:
                continue
            values.append(
                ComparisonValueView(
                    resource_id=resource_id,
                    source=source.source,
                    source_id=source.id,
                    value=value,
                    priority=priority,
                )
            )
        values.sort(key=lambda entry: (entry.priority, entry.source_id))
        # `values` rank by the DEFAULT global source order (what the merged
        # resource will use) while `status` reflects each resource's current
        # coalesced winner. These agree today; once per-field overrides exist
        # (PR #174) a resource's current winner can differ from the default --
        # expected, since a merge resets to the default order.
        resource_values = [getattr(view, field_name, None) for view in resource_views]
        comparison.append(
            FieldComparisonView(
                field=field_name,
                status=_comparison_status(resource_values),
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
    compare: Sequence[FieldComparisonView],
) -> MergeCandidateDetailView:
    # MergeCandidateDetailView is MergeCandidateView + `compare`; reuse the base
    # mapping so the shared fields stay defined in one place.
    return MergeCandidateDetailView(
        **_candidate_to_view(model).model_dump(),
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
    # here, so an APPROVED candidate's `compare` reflects the emptied originals.
    # Freezing a snapshot at approve/deny time is deferred.
    #
    # Invariant: every resource_id still exists -- merge_candidate_items FK to
    # og_field_resources and resources are never hard-deleted (merges repoint,
    # never delete). So a null-shell view always means "emptied by a merge",
    # never "missing"; no existence check is needed here. Revisit if a resource
    # hard-delete path is ever added.
    by_id = await coalesce_resources_with_sources(
        session, resource_ids, licensed_sources
    )

    # `status` compares the resources' coalesced values; `values` lists every
    # contributing source tagged with the resource it's attached to, ranked by
    # the default source order (winner-first).
    default_priority = await _default_source_priority(session)
    fallback_priority = max(default_priority.values(), default=0) + 1
    sources_with_priority = [
        (rid, source, default_priority.get(source.source, fallback_priority))
        for rid in resource_ids
        for source in by_id[rid].source_data
    ]
    resource_views = [by_id[rid].view for rid in resource_ids]
    compare = _build_comparison(resource_views, sources_with_priority)

    return _candidate_to_detail_view(candidate, compare)


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
