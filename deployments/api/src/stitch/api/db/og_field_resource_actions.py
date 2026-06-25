from collections.abc import Collection, Sequence
from typing import get_args

from fastapi import HTTPException
from sqlalchemy import func, select
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
from stitch.ogsi.model import OGFieldListItemView, OGFieldResource
from stitch.ogsi.model.types import OGSISrcKey

from .model import (
    MembershipModel,
    MembershipStatus,
    ResourceModel,
)
from .model.oil_gas_field_source_value import value_attr_for
from .queries import (
    build_coalesced_values,
    construct_resources_count_statement,
    construct_resources_query_statement,
)
from .utils import (
    coalesce_resources,
    resource_model_to_entity,
    resource_to_list_item_view,
)


_FILTER_OPTION_FIELDS: frozenset[str] = frozenset(get_args(FilterOptionField))


async def query(
    session: AsyncSession,
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> tuple[list[OGFieldListItemView], int]:
    """Query coalesced resource list items, restricted to licensed sources.

    Two-phase: a narrowed id-query (+ count) over the participating fields, then
    a single batched hydration of the returned page by id. ``params.source`` is
    ignored -- the resource universe is membership-derived and only narrowed by
    ``licensed_sources`` (source-membership existence is not a resource-level
    filter).
    """
    if params.sort_by == "source":
        raise HTTPException(
            status_code=422,
            detail="sort_by=source is not supported for resource list queries.",
        )

    ids_stmt = construct_resources_query_statement(params, licensed_sources)
    ids = list((await session.scalars(ids_stmt)).all())

    count_stmt = construct_resources_count_statement(params, licensed_sources)
    total = (
        await session.scalar(select(func.count()).select_from(count_stmt.subquery()))
        or 0
    )

    if not ids:
        return [], total

    items = await hydrate_resource_list(session, ids, licensed_sources)
    return items, total


async def hydrate_resource_list(
    session: AsyncSession,
    ids: Sequence[int],
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> list[OGFieldListItemView]:
    """Hydrate resource list items by id, coalescing in Python.

    Batched: one ``coalesce_resources`` call (constant round-trips, no N+1) over
    the page's ids -- the same Python coalescer the detail path uses -- then the
    shared ``resource_to_list_item_view`` projection. Items are returned in the
    given (phase-1) order; list ids are never repointed (the universe excludes
    them). Ids with no winning values hydrate as null-shells.
    """
    coalesced = await coalesce_resources(session, ids, licensed_sources)
    items: list[OGFieldListItemView] = []
    for rid in ids:
        view, provenance, src_data = coalesced[rid]
        resource = OGFieldResource(
            id=rid,
            source_data=src_data,
            view=view,
            provenance=provenance,
            constituents=frozenset(),
        )
        items.append(resource_to_list_item_view(resource))
    return items


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

    values_cte = build_coalesced_values(
        licensed_sources=licensed_sources, colnames=[params.field]
    )
    value_col = getattr(values_cte.c, value_attr_for(params.field))
    labeled = value_col.label("value")
    stmt = (
        select(labeled)
        .where(value_col.is_not(None), value_col != "")
        .distinct()
        .order_by(labeled)
    )
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
