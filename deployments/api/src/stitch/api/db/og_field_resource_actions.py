from collections.abc import Collection, Sequence
from typing import Any

from fastapi import HTTPException
from sqlalchemy import (
    ColumnElement,
    String,
    and_,
    asc,
    case,
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
from stitch.api.entities import OGFieldQueryParams
from stitch.api.db.og_field_source_actions import (
    attach_sources_to_resource,
    get_or_create_sources,
)
from stitch.ogsi.model import OGFieldListItemView, OGFieldResource
from stitch.ogsi.model.og_field import OilGasFieldBase
from stitch.ogsi.model.types import OGSISrcKey

from .model import (
    MembershipModel,
    MembershipStatus,
    OGFieldSourcePriority,
    OilGasFieldSourceModel,
    ResourceModel,
)
from .model.og_field_source_priority import DEFAULT_PRIORITIES
from .utils import resource_model_to_entity


_LIST_JSON_FIELDS = ("owners", "operators")
_LIST_SCALAR_FIELDS = tuple(
    field_name
    for field_name in OilGasFieldBase.model_fields
    if field_name not in _LIST_JSON_FIELDS
)
_LIST_DATA_FIELDS = (*_LIST_SCALAR_FIELDS, *_LIST_JSON_FIELDS)
_PROVENANCE_SUFFIX = "__provenance_source"


def _priority_values() -> tuple[int, ...]:
    return tuple(int(priority["priority"]) for priority in DEFAULT_PRIORITIES)


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

    coalesced = _build_licensed_resource_list_cte(params, licensed_sources)
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


def _build_licensed_resource_list_cte(
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None,
):
    s = OilGasFieldSourceModel
    m = MembershipModel
    r = ResourceModel
    p = OGFieldSourcePriority

    selected_sources = list(dict.fromkeys(params.source))
    source_join_conditions = [
        s.id == m.source_pk,
        s.source == m.source,
    ]
    if licensed_sources is not None:
        source_join_conditions.append(
            s.source.in_(list(dict.fromkeys(licensed_sources)))
        )

    qualified = (
        select(
            r.id.label("id"),
            m.source.label("source"),
            p.priority.label("priority"),
        )
        .join(m, m.resource_id == r.id)
        .join(p, p.source == m.source)
        .outerjoin(s, and_(*source_join_conditions))
        .where(
            r.repointed_id.is_(None),
            m.status == MembershipStatus.ACTIVE,
            m.source.in_(selected_sources),
        )
    )

    for field_name in _LIST_DATA_FIELDS:
        qualified = qualified.add_columns(getattr(s, field_name).label(field_name))

    qualified_cte = qualified.cte("qualified_resource_sources")
    coalesced = select(qualified_cte.c.id.label("id")).group_by(qualified_cte.c.id)

    for field_name in _LIST_SCALAR_FIELDS:
        field_col = getattr(qualified_cte.c, field_name)
        value_by_priority = [
            func.max(case((qualified_cte.c.priority == priority, field_col)))
            for priority in _priority_values()
        ]
        provenance_by_priority = [
            func.max(
                case(
                    (
                        and_(
                            qualified_cte.c.priority == priority,
                            field_col.is_not(None),
                        ),
                        qualified_cte.c.source,
                    )
                )
            )
            for priority in _priority_values()
        ]
        coalesced = coalesced.add_columns(
            func.coalesce(*value_by_priority).label(field_name),
            func.coalesce(*provenance_by_priority).label(
                f"{field_name}{_PROVENANCE_SUFFIX}"
            ),
        )

    for field_name in _LIST_JSON_FIELDS:
        value_alias = qualified_cte.alias(f"{field_name}_value_source")
        provenance_alias = qualified_cte.alias(f"{field_name}_provenance_source")
        value_col = getattr(value_alias.c, field_name)
        provenance_col = getattr(provenance_alias.c, field_name)
        value_is_present = _json_value_is_present(value_col)
        provenance_is_present = _json_value_is_present(provenance_col)

        value_subquery = (
            select(value_col)
            .where(
                value_alias.c.id == qualified_cte.c.id,
                value_is_present,
            )
            .order_by(value_alias.c.priority.asc())
            .limit(1)
            .scalar_subquery()
        )
        provenance_subquery = (
            select(provenance_alias.c.source)
            .where(
                provenance_alias.c.id == qualified_cte.c.id,
                provenance_is_present,
            )
            .order_by(provenance_alias.c.priority.asc())
            .limit(1)
            .scalar_subquery()
        )
        coalesced = coalesced.add_columns(
            value_subquery.label(field_name),
            provenance_subquery.label(f"{field_name}{_PROVENANCE_SUFFIX}"),
        )

    return coalesced.cte("licensed_resource_list")


def _json_value_is_present(col) -> ColumnElement[bool]:
    return and_(col.is_not(None), cast(col, String) != "null")


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


def _list_item_from_row(row: RowMapping) -> OGFieldListItemView:
    data = OilGasFieldBase(
        **{
            field_name: row.get(field_name)
            for field_name in OilGasFieldBase.model_fields
        }
    )
    provenance: dict[str, OGSISrcKey | None] = {
        field_name: row.get(f"{field_name}{_PROVENANCE_SUFFIX}")
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
