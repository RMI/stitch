from collections.abc import Collection, Sequence
from typing import get_args

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.status import HTTP_404_NOT_FOUND

from stitch.api.db.errors import (
    InvalidActionError,
    ResourceIntegrityError,
    ResourceNotFoundError,
)
from stitch.api.auth import CurrentUser
from stitch.api.entities import (
    FilterOptionField,
    OGFieldFilterOptionsParams,
    OGFieldQueryParams,
)
from stitch.api.db.og_field_source_actions import (
    attach_sources_to_resource,
    get_or_create_sources,
)
from stitch.ogsi.model import (
    OGFieldListItemView,
    OGFieldResource,
    OGFieldSourceValueView,
)
from stitch.ogsi.model.types import OGSISrcKey

from .model import (
    MembershipModel,
    MembershipStatus,
    OGFieldResourceSourcePriority,
    ResourceModel,
)
from .model.oil_gas_field_source_value import (
    ATTRIBUTE_NAMES,
    materialize_value,
    value_attr_for,
)
from .queries import (
    add_ranking,
    base_resource_query,
    construct_base_query_statement,
    field_source_candidates,
)
from .utils import (
    coalesce_resources,
    resource_model_to_entity,
    resource_to_list_item_view,
)


_FILTER_OPTION_FIELDS: frozenset[str] = frozenset(get_args(FilterOptionField))
_ALL_SOURCES: frozenset[OGSISrcKey] = frozenset(get_args(OGSISrcKey))


async def query(
    session: AsyncSession,
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> tuple[list[OGFieldListItemView], int]:
    """Query coalesced resource list items, restricted to licensed sources.

    A narrowed id-query (+ count) over the participating fields selects and
    orders the page, then one SQL coalesce (``coalesce_resources``) hydrates
    those ids -- values and provenance come straight from the query, with no
    second coalesce pass.
    """
    if params.sort_by == "source":
        raise HTTPException(
            status_code=422,
            detail="sort_by=source is not supported for resource list queries.",
        )

    ids_stmt = base_resource_query(params, licensed_sources)
    count_stmt = select(func.count()).select_from(ids_stmt.subquery())
    total = (await session.scalar(count_stmt)) or 0
    ids_stmt = ids_stmt.limit(params.limit).offset(params.offset)
    ids = list((await session.scalars(ids_stmt)).all())

    if not ids:
        return [], total

    # Hydrate the page with the shared SQL coalescer (same one the detail path
    # uses), then the shared list-item projection, in phase-1 order.
    coalesced = await coalesce_resources(session, ids, licensed_sources)
    items = [resource_to_list_item_view(coalesced[rid]) for rid in ids]
    return items, total


async def filter_options(
    session: AsyncSession,
    params: OGFieldFilterOptionsParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> list[str]:
    """Return distinct coalesced resource values for one filterable field.

    Reads the shared coalescing core narrowed to the single field, so values are
    priority/override-coalesced and licensed before being deduped and sorted.
    ``params.source`` is ignored (see ``query``).
    """
    if params.field not in _FILTER_OPTION_FIELDS:
        raise HTTPException(
            status_code=422,
            detail=f"field={params.field} is not supported for resource filter options.",
        )

    base_cte = construct_base_query_statement(licensed_sources)
    filtered = select(base_cte).where(base_cte.c.colname == params.field).cte()
    ranked = add_ranking(filtered).cte("ranked")
    value_col = getattr(ranked.c, value_attr_for(params.field))
    labeled = value_col.label("value")
    stmt = select(labeled).where(value_col.is_not(None)).distinct().order_by(labeled)
    values = await session.scalars(stmt)
    return list(values.all())


async def get(
    session: AsyncSession,
    id: int,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> OGFieldResource:
    stmt = (
        select(ResourceModel)
        .options(selectinload(ResourceModel.memberships))
        .where(ResourceModel.id == id)
    )
    model = await session.scalar(stmt)
    if model is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail=f"No Resource with id `{id}` found."
        )
    await session.refresh(model, ["memberships"])
    return await resource_model_to_entity(
        session, model, licensed_sources=licensed_sources
    )


async def resolve_root_id(session: AsyncSession, id: int) -> int:
    """Resolve a resource id to its terminal (root) resource id, following repoints.

    404 if ``id`` does not exist; a non-repointed id returns itself. Read-only
    endpoints use this so a request for a merged-away resource acts on the
    resource it was merged into. The write path (merges, priority edits)
    intentionally does NOT resolve -- it must act on the exact requested row.

    Resolution collapses the whole chain: ``A -> C -> F -> J`` resolves ``A`` to
    ``J``. The ``repointed_id`` graph is acyclic by construction
    (``apply_resource_merge`` always targets a brand-new row), so ``get_root``
    terminates.
    """
    model = await session.scalar(select(ResourceModel).where(ResourceModel.id == id))
    if model is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail=f"No Resource with id `{id}` found."
        )
    if model.repointed_id is None:
        return id
    try:
        return (await model.get_root(session)).id
    except ResourceNotFoundError as exc:
        # Unreachable under current invariants (FK + acyclic merges + the
        # self-reference validator), but a corrupt repoint chain must not surface
        # as an unhandled 500 on a read path.
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Resource `{id}` could not be resolved to a current resource.",
        ) from exc


async def get_resolved(
    session: AsyncSession,
    id: int,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> OGFieldResource:
    """Return resource ``id``, following repoints to the terminal (root) resource.

    Read-only wrapper over ``resolve_root_id`` + ``get``; see ``resolve_root_id``
    for the resolution semantics.
    """
    root_id = await resolve_root_id(session, id)
    return await get(session, root_id, licensed_sources=licensed_sources)


async def field_source_values(
    session: AsyncSession,
    id: int,
    field: str,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> list[OGFieldSourceValueView]:
    """Every source's value for one field of a resource, winner-first.

    Returns only sources that carry a value for ``field`` (unset omitted), in the
    same tiered per-field ranking coalescing uses -- curated (overridden) records
    first by override priority, then the rest by global default priority. The
    first entry is the coalesced winner. Licensing is applied. Each view's
    ``priority`` is its 0-based rank position (list order is authoritative);
    ``is_override`` flags the curated rows.
    """
    if field not in ATTRIBUTE_NAMES:
        raise HTTPException(
            status_code=422,
            detail=f"field={field} is not a known resource field.",
        )
    # Resolve repoints so a merged-away id returns the terminal resource's field
    # sources (and 404s a genuinely missing id), consistent with the
    # single-resource read endpoints.
    root_id = await resolve_root_id(session, id)

    # field_source_candidates ranks in SQL by the same tiered key as the coalesce
    # winner, so the row order is winner-first and rank is just the enumerate
    # index. Empty text can't be persisted, so every returned row is a real value.
    rows = (
        await session.execute(field_source_candidates(root_id, field, licensed_sources))
    ).all()
    return [
        OGFieldSourceValueView(
            source=row.source,
            source_id=row.source_pk,
            value=materialize_value(
                field,
                value_text=row.value_text,
                value_num=row.value_num,
                value_json=row.value_json,
            ),
            priority=rank,
            is_override=bool(row.is_override),
        )
        for rank, row in enumerate(rows)
    ]


async def set_field_source_priority(
    session: AsyncSession,
    user: CurrentUser,
    id: int,
    field: str,
    ordered_source_pks: Sequence[int],
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> list[OGFieldSourceValueView]:
    """Persist a curator's per-field source ordering; return the new ranking.

    ``ordered_source_pks`` must cover *exactly* the source records that currently
    carry a value for ``field`` (licensed, non-empty) -- the same set
    ``field_source_values`` returns -- each once, best-first. The save is a
    complete snapshot: every override row for ``(resource, field)`` is replaced
    with one row per record at ``priority = index``. Records added later have no
    override row, so they land in the default tier and rank last until re-curated
    (see ``add_ranking``). Writing nothing when the order is unchanged keeps the
    default tier (and its "new source ranks by default priority" behaviour) intact.
    """
    if field not in ATTRIBUTE_NAMES:
        raise HTTPException(
            status_code=422,
            detail=f"field={field} is not a known resource field.",
        )
    resource = await session.get(ResourceModel, id)
    if resource is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail=f"No Resource with id `{id}` found."
        )
    if resource.repointed_id is not None:
        raise ResourceIntegrityError(
            f"Cannot re-prioritize sources of repointed resource `{id}`."
        )
    if len(set(ordered_source_pks)) != len(ordered_source_pks):
        raise InvalidActionError("ordered_source_pks contains duplicate ids.")

    # Belt-and-suspenders behind the route's all-source-read requirement: this
    # write replaces the field's entire override set, so a caller who cannot read
    # every source could clobber rankings for sources they can't see. Require the
    # full set here too. (Revisit when partial-license reordering is supported.)
    if licensed_sources is not None and set(licensed_sources) != _ALL_SOURCES:
        raise InvalidActionError(
            "You must have read permissions for all sources to reorder a field's "
            "sources."
        )

    # Eligibility + current effective order come from the same ranked read the GET
    # endpoint uses: licensed sources with a non-empty value for the field,
    # winner-first.
    rows = (
        await session.execute(field_source_candidates(id, field, licensed_sources))
    ).all()
    current_order = [row.source_pk for row in rows]
    eligible = set(current_order)
    requested = set(ordered_source_pks)
    if requested != eligible:
        raise InvalidActionError(
            "ordered_source_pks must cover exactly the sources with a value for "
            f"field {field!r} (missing={sorted(eligible - requested)}, "
            f"unexpected={sorted(requested - eligible)})."
        )

    # No-op: the requested order already matches the effective order, so persist
    # nothing (and leave any records in the default tier there).
    if list(ordered_source_pks) == current_order:
        return await field_source_values(session, id, field, licensed_sources)

    source_by_pk = {row.source_pk: row.source for row in rows}
    await session.execute(
        delete(OGFieldResourceSourcePriority).where(
            OGFieldResourceSourcePriority.resource_id == id,
            OGFieldResourceSourcePriority.colname == field,
        )
    )
    for priority, source_pk in enumerate(ordered_source_pks):
        session.add(
            OGFieldResourceSourcePriority.create(
                created_by=user,
                resource_id=id,
                source=source_by_pk[source_pk],
                source_pk=source_pk,
                colname=field,
                priority=priority,
            )
        )
    await session.flush()
    return await field_source_values(session, id, field, licensed_sources)


async def create(
    session: AsyncSession, user: CurrentUser, resource: OGFieldResource
) -> OGFieldResource:
    """
    Here we create a resource either from new source data or existing source data. It's also possible
    to create an empty resource with no reference to source data.

    - create the resource
    - create the sources
    - create membership
    """
    if resource.repointed_to is not None:
        raise ResourceIntegrityError(
            f"Cannot create resource that has been repointed.\n\tNew: {repr(resource)}"
        )
    model = ResourceModel.create(created_by=user)
    session.add(model)
    await session.flush()
    if resource.source_data:
        src_models = await get_or_create_sources(session, user, resource.source_data)
        res = await attach_sources_to_resource(
            session=session, resource_id=model.id, source_rows=src_models, user=user
        )
        return res
    await session.refresh(model, ["memberships"])
    return await resource_model_to_entity(session, model)


async def apply_resource_merge(
    session: AsyncSession,
    user: CurrentUser,
    resource_ids: Sequence[int],
) -> OGFieldResource:
    """
    Stub "merge" behavior:
    - Treat ids[0] as the canonical/target resource.
    - Update all resources in ids[1:] to have repointed_id = ids[0].

    NOTE: This only updates the resource table repointing field (no membership/source consolidation).
    """
    # preserve order but drop duplicates
    unique_ids = list(dict.fromkeys(resource_ids))
    if len(unique_ids) < 2:
        raise InvalidActionError(
            f"Merging only possible between multiple ids: received: {unique_ids}"
        )

    stmt = select(ResourceModel).where(ResourceModel.id.in_(unique_ids))

    results = (await session.scalars(stmt)).all()
    missing_ids = set(unique_ids).difference(set([r.id for r in results]))
    if len(missing_ids) > 0:
        msg = f"Resources not found for ids: [{','.join(map(str, missing_ids))}]"
        raise ResourceNotFoundError(msg)

    if len(repointed := [r for r in results if r.repointed_id is not None]) > 0:
        reprs = map(repr, repointed)
        msg = f"Repointed: [{','.join(reprs)}]"
        raise ResourceIntegrityError(
            f"Cannot merge any resource that has already been merged. {msg}"
        )

    # all ids exist, none have already been repointed
    #
    # The merge target is a brand-new resource with no rows in
    # og_field_resource_source_priority, so it resolves fields in the default
    # global source order. Any per-field/per-resource priority overrides on the
    # originals are intentionally NOT carried over -- merging resets ordering to
    # default. (No-op reset today since the target is fresh; a later PR handles
    # an explicit reset if merge semantics ever preserve an existing resource.)
    new_resource = ResourceModel.create(created_by=user)
    session.add(new_resource)
    await session.flush()

    # all results are still members of the session
    # changes will be picked up on commit
    for res in results:
        res.repointed_id = new_resource.id

    _ = await _repoint_memberships(session, user, new_resource.id, unique_ids)

    # Return the canonical resource entity
    await session.refresh(new_resource, ["memberships"])
    return await resource_model_to_entity(session, new_resource)


async def _repoint_memberships(
    session: AsyncSession,
    user: CurrentUser,
    to_id: int,
    from_ids: Sequence[int],
) -> Sequence[MembershipModel]:
    """Create new memberships pointing to a different resource.

    Collect all memberships whose `resource_id` is in the `from_resoure_ids` argument. For each of these, create
    a new membership where `resource_id` = `to_resource_id`.

    This all takes place after an approved merge candidate is applied and a new ResourceModel is created.

    Args:
        session: the db session
        user: the logged in user
        to_id: the new resource id
        from_ids: the original resource_ids

    Returns:
        Sequence of newly created `MembershipModel` objects.
    """
    res = await session.get(ResourceModel, to_id)
    if res is None:
        raise ResourceNotFoundError(f"No resource found for id = {to_id}.")

    existing_memberships = (
        await session.scalars(
            select(MembershipModel).where(MembershipModel.resource_id.in_(from_ids))
        )
    ).all()

    # create new memberships pointing to the new resource
    new_memberships: list[MembershipModel] = []
    for mem in existing_memberships:
        # set status on
        new_memberships.append(
            MembershipModel.create(
                created_by=user,
                resource_id=res.id,
                source=mem.source,
                source_pk=mem.source_pk,
                status=mem.status,
            )
        )
        if mem.status == MembershipStatus.ACTIVE:
            mem.status = MembershipStatus.INACTIVE
    session.add_all(new_memberships)
    return new_memberships
