import asyncio
from collections.abc import Sequence
from functools import partial
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.status import HTTP_404_NOT_FOUND

from stitch.api.db.errors import ResourceIntegrityError
from stitch.api.auth import CurrentUser
from stitch.api.db.og_field_source_actions import (
    attach_sources_to_resource,
    get_or_create_sources,
)
from stitch.api.entities import (
    Resource,
)

from .model import (
    ResourceModel,
)
from .utils import resource_model_to_entity


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


async def create(session: AsyncSession, user: CurrentUser, resource: Resource):
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
