from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_404_NOT_FOUND

from stitch.api.auth import CurrentUser
from stitch.api.db import resource_actions
from stitch.api.db.config import UnitOfWorkDep
from stitch.api.db.model import OilGasFieldModel

from stitch.ogsi.model.og_field import OilGasFieldBase  # request model
from stitch.ogsi.model import OGFieldView  # response model

router = APIRouter(prefix="/oil-gas-fields", tags=["oil_gas_fields"])


@router.post("/", response_model=OGFieldView)
async def create_oil_gas_field(
    payload: OilGasFieldBase,
    uow: UnitOfWorkDep,
    user: CurrentUser,
):
    session: AsyncSession = uow.session

    # Create the generic resource first (label derived from OG name)
    created_res = await resource_actions.create(
        session=session,
        user=user,
        resource=resource_actions.CreateResource(
            name=payload.name
        ),  # adjust import if CreateResource lives elsewhere in your branch
    )

    og = OilGasFieldModel(
        resource_id=created_res.id,
        created_by_id=user.id,
        last_updated_by_id=user.id,
    )
    og.payload = payload
    session.add(og)
    await session.flush()

    # Package response type
    return OGFieldView(id=og.resource_id, **payload.model_dump())


@router.get("/", response_model=Sequence[OGFieldView])
async def list_oil_gas_fields(uow: UnitOfWorkDep):
    session: AsyncSession = uow.session
    rows = (await session.execute(select(OilGasFieldModel))).scalars().all()

    out: list[OGFieldView] = []
    for row in rows:
        p = row.payload
        out.append(OGFieldView(id=row.resource_id, **p.model_dump()))
    return out


@router.get("/{id}", response_model=OGFieldView)
async def get_oil_gas_field(id: int, uow: UnitOfWorkDep):
    session: AsyncSession = uow.session
    row = await session.get(OilGasFieldModel, id)
    if row is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"No OilGasField with id `{id}` found.",
        )

    p = row.payload
    return OGFieldView(id=row.resource_id, **p.model_dump())
