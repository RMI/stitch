import asyncio
from collections import defaultdict
from collections.abc import Mapping, Sequence
from functools import partial
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.status import HTTP_404_NOT_FOUND

from stitch.api.db.model.sources import SOURCE_TABLES, SourceModel
from stitch.api.auth import CurrentUser
from stitch.api.entities import (
    CreateResource,
    CreateResourceSourceData,
    CreateSourceData,
    Resource,
    SourceData,
    SourceKey,
)

from .model import (
    MembershipModel,
    ResourceModel,
)
from stitch.ogsi.model.og_field import OilGasFieldBase


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
    og_fields = tuple(OilGasFieldBase.from_entity(og_field) for og_field in data.og_field)

    session.add_all(og_fields)
    await session.flush()
    return SourceData(
        og_field={g.id: g.as_entity() for g in og_fields},
    )
