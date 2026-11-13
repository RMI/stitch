from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
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
from stitch.api.observability.context import named_query
from stitch.ogsi.model import OGFieldSource
from stitch.ogsi.model.og_field import OilGasFieldBase
from stitch.ogsi.model.types import OGSISrcKey

from .model import (
    MergeCandidateItemModel,
    MergeCandidateModel,
    OGFieldResourceState,
    OGFieldSourcePriority,
    ResourceModel,
)
from .og_field_resource_actions import apply_resource_merge, profile_mask
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
        moved = ", ".join(
            f"resource {r.id} is now resource {r.repointed_id}" for r in repointed
        )
        raise ResourceIntegrityError(
            f"Cannot merge any resource that has already been merged: {moved}."
        )

    return results


def _fingerprint(resource_ids: Sequence[int]) -> str:
    return ":".join(map(str, sorted(set(resource_ids))))


def _candidate_to_view(
    model: MergeCandidateModel, display_name: str | None = None
) -> MergeCandidateView:
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
        display_name=display_name,
    )


# resource id -> (coalesced name, default priority of the source it came from;
# None when that source has no default priority)
NamedResources = dict[int, tuple[str, int | None]]


def _pick_display_name(model: MergeCandidateModel, names: NamedResources) -> str | None:
    """The name the Merge Review queue shows for one candidate.

    Once merged, the source resources are emptied, so the merged resource's
    name wins. Otherwise the name from the best-ranked source wins (lower
    priority is better; unranked sources sort last), with ties going to the
    earlier resource in the candidate. ``None`` when no resource has a name.
    """
    if model.merged_resource_id in names:
        return names[model.merged_resource_id][0]
    best: tuple[tuple[bool, int], str] | None = None
    for item in sorted(model.items, key=lambda i: i.position):
        entry = names.get(item.resource_id)
        if entry is None:
            continue
        name, priority = entry
        rank = (priority is None, priority or 0)
        if best is None or rank < best[0]:
            best = (rank, name)
    return best[1] if best else None


async def _load_resource_names(session: AsyncSession, mask: int) -> NamedResources:
    """Coalesced name, and the default priority of the source it came from,
    from the read model for every resource any merge candidate references (its
    items, or the resource it merged into).

    The ids are selected inside the query rather than passed in, so the
    statement stays the same size however many candidates exist. Resources
    with no name (or no row -- e.g. emptied by a merge) are left out.
    """
    state = OGFieldResourceState
    rows = await session.execute(
        select(state.resource_id, state.name, OGFieldSourcePriority.priority)
        .outerjoin(
            OGFieldSourcePriority,
            OGFieldSourcePriority.source == state.provenance["name"].as_string(),
        )
        .where(
            state.permission_mask == mask,
            or_(
                state.resource_id.in_(select(MergeCandidateItemModel.resource_id)),
                state.resource_id.in_(
                    select(MergeCandidateModel.merged_resource_id).where(
                        MergeCandidateModel.merged_resource_id.is_not(None)
                    )
                ),
            ),
        )
    )
    return {
        resource_id: (name, priority)
        for resource_id, name, priority in rows.all()
        if name is not None
    }


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
        # resource will use -- a merge drops per-resource overrides), while
        # `status` reflects each resource's current effective coalesced value.
        # These can already differ whenever a per-resource priority override is
        # active (the coalescer uses COALESCE(override, default)): values[0] is
        # the post-merge winner, not necessarily the resource's current one.
        # Expected, not a bug.
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


async def list_merge_candidates(
    session: AsyncSession,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> list[MergeCandidateView]:
    """Every merge candidate, newest first, each with its queue display name.

    Names come from the precomputed read model for the caller's permission
    profile (one query for the whole list), so the queue never has to load
    each resource's details. 403 if the caller matches no profile, like the
    oil & gas field list.
    """
    mask = profile_mask(licensed_sources, refused_action="list merge candidates")
    stmt = (
        select(MergeCandidateModel)
        .options(selectinload(MergeCandidateModel.items))
        .order_by(MergeCandidateModel.created.desc())
    )
    with named_query("merge_candidates.list"):
        candidates = (await session.scalars(stmt)).all()

    with named_query("merge_candidates.list.names"):
        names = await _load_resource_names(session, mask) if candidates else {}
    return [_candidate_to_view(c, _pick_display_name(c, names)) for c in candidates]


async def get_merge_candidate(
    session: AsyncSession,
    candidate_id: int,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> MergeCandidateDetailView:
    with named_query("merge_candidates.detail.load"):
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
    with named_query("merge_candidates.detail.coalesce"):
        by_id = await coalesce_resources_with_sources(
            session, resource_ids, licensed_sources
        )

    # `status` compares the resources' coalesced values; `values` lists every
    # contributing source tagged with the resource it's attached to, ranked by
    # the default source order (winner-first).
    with named_query("merge_candidates.detail.default_priority"):
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
    with named_query("merge_candidates.create.load_resources"):
        await _load_mergeable_resources(session, resource_ids)

    fingerprint = _fingerprint(resource_ids)
    with named_query("merge_candidates.create.check_existing"):
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

    with named_query("merge_candidates.create.persist"):
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


async def groups_without_candidates(
    session: AsyncSession, groups: Sequence[Sequence[int]]
) -> list[Sequence[int]]:
    """The groups that don't already have a merge candidate (any status).

    Compares fingerprints (the sorted, de-duplicated resource ids), which every
    write keeps in step with a candidate's items, so this reads one column
    rather than loading every candidate and its items.
    """
    with named_query("merge_candidates.existing_fingerprints"):
        existing = set(
            (await session.scalars(select(MergeCandidateModel.fingerprint))).all()
        )
    return [group for group in groups if _fingerprint(group) not in existing]


async def create_merge_candidates_bulk(
    session: AsyncSession,
    user: CurrentUser,
    groups: Sequence[Sequence[int]],
) -> None:
    with named_query("merge_candidates.bulk_create"):
        candidates = [
            MergeCandidateModel.create(created_by=user, fingerprint=_fingerprint(group))
            for group in groups
        ]
        session.add_all(candidates)
        await session.flush()

        session.add_all(
            [
                MergeCandidateItemModel(
                    merge_candidate_id=candidate.id,
                    resource_id=resource_id,
                    position=position,
                )
                for candidate, group in zip(candidates, groups)
                for position, resource_id in enumerate(group)
            ]
        )
        await session.flush()


async def _reroute_pending_candidates(
    session: AsyncSession,
    user: CurrentUser,
    merged_away_ids: Sequence[int],
    new_id: int,
) -> None:
    """Repoint other PENDING candidates off resources that a merge just consumed.

    Approving a candidate merges ``merged_away_ids`` into the brand-new resource
    ``new_id`` and repoints the originals. Any *other* PENDING candidate that
    still references one of those originals would otherwise be stranded: its
    comparison would coalesce an emptied null-shell, and its own approval would
    fail the already-merged guard, leaving Deny as the only (dishonest) exit.

    Instead, rewrite each such candidate in place to reference ``new_id``. It
    stays PENDING and reviewable, and because ``get_merge_candidate`` builds the
    comparison live from the stored item rows, the review pane immediately shows
    ``new_id``'s current values. Rides the caller's transaction.

    Call this *after* the approved candidate has been marked APPROVED: the query
    below autoflushes that status change, so the ``status == PENDING`` filter
    excludes it on its own and no explicit exclude id is needed.
    """
    merged_away = set(merged_away_ids)
    # Targeted query: only candidates that actually reference a merged-away
    # resource can be stale, so join through the items and filter on
    # ``resource_id`` rather than scanning every PENDING candidate.
    stmt = (
        select(MergeCandidateModel)
        .join(
            MergeCandidateItemModel,
            MergeCandidateItemModel.merge_candidate_id == MergeCandidateModel.id,
        )
        .where(
            MergeCandidateItemModel.resource_id.in_(merged_away),
            MergeCandidateModel.status == MergeCandidateStatus.PENDING,
        )
        .options(selectinload(MergeCandidateModel.items))
        .distinct()
    )
    candidates = (await session.scalars(stmt)).all()
    if not candidates:
        return

    # A rerouted candidate always contains new_id, which is brand-new, so its
    # fingerprint cannot collide with any pre-existing candidate -- only with
    # another candidate rerouted in this same pass (e.g. A+C and B+C both become
    # D+C). Track survivors' member sets and drop later duplicates: they are now
    # the identical proposal. Order by id so the survivor is deterministic.
    kept: set[str] = set()
    for candidate in sorted(candidates, key=lambda c: c.id):
        # Rewrite each merged-away member to new_id. If a candidate held more than
        # one merged-away id (e.g. approving A+B collapses a member of A+B+C),
        # they all collapse to new_id; drop the duplicate items to respect the
        # (candidate, resource_id) unique constraint.
        seen_ids: set[int] = set()
        new_ids: list[int] = []
        for item in sorted(candidate.items, key=lambda i: i.position):
            target = new_id if item.resource_id in merged_away else item.resource_id
            if target in seen_ids:
                # Removing from the delete-orphan collection deletes the row on
                # flush and keeps candidate.items consistent in memory.
                candidate.items.remove(item)
                continue
            item.resource_id = target
            seen_ids.add(target)
            new_ids.append(target)

        # Delete the candidate when it can no longer stand on its own:
        #   * fewer than two members -- it was a subset of the approved candidate
        #     (e.g. A+B when A+B+C is approved), collapsed to just [new_id], and a
        #     single-member candidate can never be approved (_normalize_resource_ids
        #     requires >=2). It is fully subsumed by the approval anyway.
        #   * a member set already kept this pass -- it is now the identical
        #     proposal as an earlier survivor.
        fingerprint = _fingerprint(new_ids)
        if len(new_ids) < 2 or fingerprint in kept:
            await session.delete(candidate)
            continue
        kept.add(fingerprint)
        candidate.fingerprint = fingerprint
        candidate.last_updated_by_id = user.id

    await session.flush()


async def approve_merge_candidate(
    session: AsyncSession,
    user: CurrentUser,
    candidate_id: int,
    request: MergeCandidateReviewRequest | None = None,
) -> MergeCandidateView:
    with named_query("merge_candidates.approve.load"):
        candidate = await _load_candidate_model(session, candidate_id)
    if candidate.status != MergeCandidateStatus.PENDING:
        raise InvalidActionError(
            f"Merge candidate {candidate_id} is not pending; current status={candidate.status}."
        )

    resource_ids = [
        item.resource_id for item in sorted(candidate.items, key=lambda i: i.position)
    ]
    with named_query("merge_candidates.approve.load_resources"):
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

    # Reroute after marking this candidate APPROVED: the reroute query autoflushes
    # the status change, so its PENDING filter excludes this candidate on its own.
    await _reroute_pending_candidates(
        session=session,
        user=user,
        merged_away_ids=resource_ids,
        new_id=merged_resource.id,
    )

    with named_query("merge_candidates.approve.persist"):
        await session.flush()
        candidate = await _load_candidate_model(session, candidate_id)
    return _candidate_to_view(candidate)


async def deny_merge_candidate(
    session: AsyncSession,
    user: CurrentUser,
    candidate_id: int,
    request: MergeCandidateReviewRequest | None = None,
) -> MergeCandidateView:
    with named_query("merge_candidates.deny.load"):
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
    with named_query("merge_candidates.deny.persist"):
        await session.flush()
        candidate = await _load_candidate_model(session, candidate_id)
    return _candidate_to_view(candidate)
