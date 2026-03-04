import asyncio
from collections import defaultdict
from collections.abc import Mapping, Sequence
from functools import partial
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.status import HTTP_404_NOT_FOUND

from .model.sources import SOURCE_TABLES, SourceModel
from stitch.api.auth import CurrentUser
from stitch.api.entities import (
    CreateResource,
    CreateResourceSourceData,
    CreateSourceData,
    Resource,
    SourceData,
    SourceKey,
)

from .errors import InvalidActionError, ResourceNotFoundError, ResourceIntegrityError

from .model import (
    CCReservoirsSourceModel,
    GemSourceModel,
    MembershipModel,
    MembershipStatus,
    RMIManualSourceModel,
    ResourceModel,
    WMSourceModel,
)


async def get_or_create_source_models(
    session: AsyncSession,
    data: CreateResourceSourceData,
) -> Mapping[SourceKey, Sequence[SourceModel]]:
    result: dict[SourceKey, list[SourceModel]] = defaultdict(list)
    for key, model_cls in SOURCE_TABLES.items():
        for item in data.get(key):
            if isinstance(item, int):
                src_model = await session.get(model_cls, item)
                if src_model is None:
                    continue
                result[key].append(src_model)
            else:
                result[key].append(model_cls.from_entity(item))
    return result


def resource_model_to_empty_entity(model: ResourceModel):
    return Resource(
        id=model.id,
        name=model.name,
        country=model.country,
        source_data=SourceData(),
        constituents=[],
        created=model.created,
        updated=model.updated,
    )


async def resource_model_to_entity(
    session: AsyncSession, model: ResourceModel
) -> Resource:
    source_model_data = await model.get_source_data(session)
    source_data = SourceData.model_validate(source_model_data)
    constituent_models = await ResourceModel.get_constituents_by_root_id(
        session, model.id
    )
    constituents = [
        resource_model_to_empty_entity(cm)
        for cm in constituent_models
        if cm.id != model.id
    ]
    return Resource(
        id=model.id,
        name=model.name,
        country=model.country,
        source_data=source_data,
        constituents=constituents,
        created=model.created,
        updated=model.updated,
    )


async def get_all(session: AsyncSession) -> Sequence[Resource]:
    stmt = (
        select(ResourceModel)
        .where(ResourceModel.repointed_id.is_(None))
        .options(selectinload(ResourceModel.memberships))
    )
    models = (await session.scalars(stmt)).all()
    fn = partial(resource_model_to_entity, session)
    return await asyncio.gather(*[fn(m) for m in models])


async def get(session: AsyncSession, id: int):
    model = await session.get(ResourceModel, id)
    if model is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail=f"No Resource with id `{id}` found."
        )
    await session.refresh(model, ["memberships"])
    return await resource_model_to_entity(session, model)


async def create(session: AsyncSession, user: CurrentUser, resource: CreateResource):
    """
    Here we create a resource either from new source data or existing source data. It's also possible
    to create an empty resource with no reference to source data.

    - create the resource
    - create the sources
    - create membership
    """
    model = ResourceModel.create(
        created_by=user, name=resource.name, country=resource.country
    )
    session.add(model)
    if resource.source_data:
        src_model_groups = await get_or_create_source_models(
            session, resource.source_data
        )
        for src_key, src_models in src_model_groups.items():
            session.add_all(src_models)
            await session.flush()
            for src_model in src_models:
                session.add(
                    MembershipModel.create(
                        created_by=user,
                        resource=model,
                        source=src_key,
                        source_pk=src_model.id,
                    )
                )
    await session.flush()
    await session.refresh(model, ["memberships"])
    return await resource_model_to_entity(session, model)


async def create_source_data(session: AsyncSession, data: CreateSourceData):
    """
    For bulk inserting data into source tables.
    """
    gems = tuple(GemSourceModel.from_entity(gem) for gem in data.gem)
    wms = tuple(WMSourceModel.from_entity(wm) for wm in data.wm)
    rmis = tuple(RMIManualSourceModel.from_entity(rmi) for rmi in data.rmi)
    ccs = tuple(CCReservoirsSourceModel.from_entity(cc) for cc in data.cc)

    session.add_all(gems + wms + rmis + ccs)
    await session.flush()
    return SourceData(
        gem={g.id: g.as_entity() for g in gems},
        wm={wm.id: wm.as_entity() for wm in wms},
        rmi={rmi.id: rmi.as_entity() for rmi in rmis},
        cc={cc.id: cc.as_entity() for cc in ccs},
    )


async def merge_resources(
    session: AsyncSession,
    user: CurrentUser,
    resource_ids: Sequence[int],
) -> Resource:
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
):
    """Create new memberships pointing to a different resource.

    Collect all memberships whose `resource_id` is in the `from_resoure_ids` argument. For each of these, create
    a new membership where `resource_id` = `to_resource_id`.

    This all takes place after a `merge_resources` operation where a new ResourceModel is created.

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

    # TODO: any integrity checks? What constitutes an invalid state at this point

    # create new memberships pointing to the new resource
    new_memberships: list[MembershipModel] = []
    for mem in existing_memberships:
        # set status on
        new_memberships.append(
            MembershipModel.create(
                created_by=user,
                resource=res,
                source=mem.source,
                source_pk=mem.source_pk,
                status=mem.status,
            )
        )
        if mem.status == MembershipStatus.ACTIVE:
            mem.status = MembershipStatus.INACTIVE
    session.add_all(new_memberships)
    return new_memberships
