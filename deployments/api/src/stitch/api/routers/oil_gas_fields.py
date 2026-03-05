from __future__ import annotations

from typing import Any
from collections.abc import Sequence

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_404_NOT_FOUND

from stitch.api.auth import CurrentUser
from stitch.api.db import resource_actions, og_field_source_actions
from stitch.api.db.config import UnitOfWorkDep
from stitch.api.db.model import OilGasFieldSourceModel
from stitch.api.db.og_field_source_actions import create_source, attach_to_resource
from stitch.api.resources.entities import CreateResource, Resource

from stitch.ogsi.model.og_field import OilGasFieldBase  # request model
from stitch.ogsi.model import OGFieldView  # response model

router = APIRouter(prefix="/oil-gas-fields", tags=["oil_gas_fields"])


@router.post("/", response_model=Resource)
async def create_oil_gas_field(
    raw_body: dict[str, object],
    uow: UnitOfWorkDep,
    user: CurrentUser,
):
    session = uow.session

    # 1) create a generic resource
    resource = await resource_actions.create(
        session=session,
        user=user,
        resource=CreateResource(name=raw_body.get("name"))
    )

    # 2) create canonical domain source
    src = await create_source(
        session=session,
        raw_payload=raw_body,
        source_system=raw_body.get("source_system"),
    )

    # 3) attach it via membership
    await attach_to_resource(session, resource.id, src, user)

    return resource

@router.get("/", response_model=list[Resource])
async def list_oil_gas_fields(uow: UnitOfWorkDep, user: CurrentUser):
    return await og_field_source_actions.list_og_resources(session=uow.session)


@router.get("/{id}", response_model=Resource)
async def get_oil_gas_field(id: int, uow: UnitOfWorkDep, user: CurrentUser):
    return await resource_actions.get(session=uow.session, id=id)
