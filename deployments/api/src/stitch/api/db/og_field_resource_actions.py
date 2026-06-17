import json
from collections.abc import Collection, Sequence
from typing import Any, get_args

from fastapi import HTTPException
from sqlalchemy import (
    ColumnElement,
    String,
    asc,
    cast,
    desc,
    func,
    or_,
    select,
)
from sqlalchemy.engine import RowMapping
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
from stitch.ogsi.model.og_field import OilGasFieldBase
from stitch.ogsi.model.types import OGSISrcKey

from .coalesce_sql import PROVENANCE_SUFFIX, build_resource_list_cte
from .model import (
    MembershipModel,
    MembershipStatus,
    OilGasFieldSourceModel,
    ResourceModel,
)
from .model.oil_gas_field_source_value import JSON_ATTRIBUTE_NAMES
from .utils import resource_model_to_entity


_FILTER_OPTION_FIELDS: frozenset[str] = frozenset(get_args(FilterOptionField))


async def query(
    session: AsyncSession,
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> tuple[list[OGFieldListItemView], int]:
    """Query coalesced resource list items, restricted to licensed sources."""
    if params.sort_by == "source":
        raise HTTPException(
            status_code=422,
            detail="sort_by=source is not supported for resource list queries.",
        )

    coalesced = build_resource_list_cte(params.source, licensed_sources)
    filtered = select(coalesced)
    for condition in _build_final_conditions(coalesced, params):
        filtered = filtered.where(condition)

    total_stmt = select(func.count()).select_from(filtered.subquery())
    total = await session.scalar(total_stmt) or 0

    page_stmt = (
        filtered.order_by(*_build_sort_clauses(coalesced, params))
        .offset(params.offset)
        .limit(params.limit)
    )
    rows = (await session.execute(page_stmt)).mappings().all()

    return [_list_item_from_row(row) for row in rows], total


async def filter_options(
    session: AsyncSession,
    params: OGFieldFilterOptionsParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> list[str]:
    """Return distinct coalesced resource values for one filterable field."""
    if params.field not in _FILTER_OPTION_FIELDS:
        raise HTTPException(
            status_code=422,
            detail=f"field={params.field} is not supported for resource filter options.",
        )

    coalesced = build_resource_list_cte(params.source, licensed_sources)
    col = _resource_list_column(coalesced, params.field)
    if col is None:
        raise HTTPException(
            status_code=422,
            detail=f"field={params.field} is not supported for resource filter options.",
        )

    value_col = cast(col, String).label("value")
    stmt = (
        select(value_col)
        .where(col.is_not(None), cast(col, String) != "")
        .distinct()
        .order_by(value_col)
    )
    values = await session.scalars(stmt)
    return list(values.all())


def _build_final_conditions(
    coalesced,
    params: OGFieldQueryParams,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []

    if params.q:
        q_term = f"%{params.q}%"
        q_conditions: list[ColumnElement[bool]] = []
        for field_name in OilGasFieldSourceModel._q_fields:
            col = getattr(coalesced.c, field_name, None)
            if col is not None:
                q_conditions.append(col.ilike(q_term))
        if q_conditions:
            conditions.append(or_(*q_conditions))

    for field_name in OilGasFieldSourceModel._exact_match_fields:
        value = getattr(params, field_name, None)
        if value is None:
            continue
        col = _resource_list_column(coalesced, field_name)
        if col is not None:
            conditions.append(col == value)

    return conditions


def _build_sort_clauses(coalesced, params: OGFieldQueryParams) -> list[Any]:
    sort_col = _resource_list_column(coalesced, params.sort_by)
    clauses: list[Any] = []
    if sort_col is not None:
        direction = desc if params.sort_order == "desc" else asc
        clauses.append(direction(sort_col).nulls_last())
    if params.sort_by not in {"id", "resource_id"}:
        clauses.append(asc(coalesced.c.id))
    return clauses


def _resource_list_column(coalesced, field_name: str):
    if field_name == "resource_id":
        return coalesced.c.id
    return getattr(coalesced.c, field_name, None)


def _row_field_value(row: RowMapping, field_name: str):
    """Read a coalesced field, deserializing JSON-typed fields emitted as text."""
    value = row.get(field_name)
    if field_name in JSON_ATTRIBUTE_NAMES and isinstance(value, str):
        return json.loads(value)
    return value


def _list_item_from_row(row: RowMapping) -> OGFieldListItemView:
    data = OilGasFieldBase(
        **{
            field_name: _row_field_value(row, field_name)
            for field_name in OilGasFieldBase.model_fields
        }
    )
    provenance: dict[str, OGSISrcKey | None] = {
        field_name: row.get(f"{field_name}{PROVENANCE_SUFFIX}")
        for field_name in OilGasFieldBase.model_fields
    }
    return OGFieldListItemView(id=row["id"], data=data, provenance=provenance)


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
