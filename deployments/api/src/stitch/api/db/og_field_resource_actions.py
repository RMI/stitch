from collections.abc import Sequence
from itertools import groupby

from fastapi import HTTPException
from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.status import HTTP_404_NOT_FOUND

from stitch.api.coalesce import ProvAttrs, coalesce_og_field_resource
from stitch.api.db.errors import (
    InvalidActionError,
    ResourceIntegrityError,
    ResourceNotFoundError,
)
from stitch.api.auth import CurrentUser
from stitch.api.db.model.resource_coalesced_view import ResourceCoalescedView
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
from .utils import resource_model_to_entity


async def query(
    session: AsyncSession,
    params: OGFieldQueryParams,
) -> tuple[list[OGFieldListItemView], int]:
    """Query coalesced view for list items with provenance."""
    views = await ResourceCoalescedView.query(session, params)
    total = await ResourceCoalescedView.count(session, params)
    if not views:
        return [], total

    resource_ids = [v.id for v in views]
    prov_map = await _load_provenance(session, resource_ids)

    items: list[OGFieldListItemView] = []
    for v in views:
        data = OilGasFieldBase(
            **{f: getattr(v, f, None) for f in OilGasFieldBase.model_fields}
        )
        raw_prov = prov_map.get(v.id, {})
        provenance: dict[str, OGSISrcKey | None] = {
            k: (None if val is None else val[1]) for k, val in raw_prov.items()
        }
        items.append(OGFieldListItemView(id=v.id, data=data, provenance=provenance))

    return items, total


async def _load_provenance(
    session: AsyncSession, resource_ids: Sequence[int]
) -> dict[int, ProvAttrs]:
    """Batch-load provenance for resources via memberships → sources → coalesce."""
    stmt = (
        select(MembershipModel.resource_id, OilGasFieldSourceModel)
        .join(
            OilGasFieldSourceModel,
            MembershipModel.source_pk == OilGasFieldSourceModel.id,
        )
        .where(MembershipModel.resource_id.in_(resource_ids))
        .where(MembershipModel.status == MembershipStatus.ACTIVE)
        .order_by(MembershipModel.resource_id)
    )
    rows: Sequence[Row[tuple[int, OilGasFieldSourceModel]]] = (
        await session.execute(stmt)
    ).all()
    priorities = (
        await session.scalars(
            select(OGFieldSourcePriority.source).order_by(
                OGFieldSourcePriority.priority
            )
        )
    ).all()

    result: dict[int, ProvAttrs] = {}
    for rid, group in groupby(rows, key=lambda r: r[0]):
        sources = [src.as_entity() for _, src in group]
        _, prov = coalesce_og_field_resource(sources, priorities)
        result[rid] = prov

    return result


async def get(session: AsyncSession, id: int) -> OGFieldResource:
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
    return await resource_model_to_entity(session, model)


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
