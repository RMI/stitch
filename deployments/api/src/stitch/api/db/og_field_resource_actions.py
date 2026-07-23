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
from stitch.ogsi.model import (
    OGFieldListItemView,
    OGFieldResource,
    OGFieldSourceValueView,
)
from stitch.ogsi.model.types import OGSISrcKey

from .model import (
    MembershipModel,
    MembershipStatus,
    ResourceModel,
)
from .model.oil_gas_field_source_value import ATTRIBUTE_NAMES, value_attr_for
from .queries import base_resource_query, construct_base_query_statement, add_ranking
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


async def field_source_values(
    session: AsyncSession,
    id: int,
    field: str,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> list[OGFieldSourceValueView]:
    """Every source's value for one field of a resource, best-priority first.

    Returns only sources that carry a value for ``field`` (unset omitted),
    each with its effective per-resource priority. The first entry is the
    coalesced winner. Licensing is applied. Priority is source-scoped today; the
    contract is unchanged when it becomes resource/field-scoped.
    """
    if field not in ATTRIBUTE_NAMES:
        raise HTTPException(
            status_code=422,
            detail=f"field={field} is not a known resource field.",
        )
    if await session.get(ResourceModel, id) is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail=f"No Resource with id `{id}` found."
        )

    # source_data_by_resource_id returns rows best-priority-first (ordered in
    # SQL by the same (priority, source, source_pk) as the coalesce ranking), so
    # dropping sources with no value for the field preserves winner-first order
    # -- the first entry is the coalesced winner. Empty strings are never
    # persisted (absent == unset), so a null check alone is enough.
    by_id = await ResourceModel.source_data_by_resource_id(
        session, [id], licensed_sources
    )
    return [
        OGFieldSourceValueView(
            source=src.source, id=src.id, value=value, priority=priority
        )
        for src, priority in by_id.get(id, [])
        if src.id is not None and (value := getattr(src, field)) is not None
    ]


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
