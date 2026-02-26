from collections.abc import Sequence

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_404_NOT_FOUND

from stitch.api.auth import CurrentUser
from stitch.api.entities import CreateOilGasField, OilGasField
from stitch.api.db.model.oilgas_field import OilGasFieldModel


async def get_all(*, session: AsyncSession) -> Sequence[OilGasField]:
    stmt = select(OilGasFieldModel)
    models = (await session.scalars(stmt)).all()
    # from_attributes=True on OilGasField makes this work cleanly
    return [OilGasField.model_validate(m) for m in models]


async def get(*, session: AsyncSession, id: int) -> OilGasField:
    model = await session.get(OilGasFieldModel, id)
    if model is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"No OilGasField with id `{id}` found.",
        )
    return OilGasField.model_validate(model)


async def create(
    *,
    session: AsyncSession,
    user: CurrentUser,
    oilgas_field: CreateOilGasField,
) -> OilGasField:
    model = OilGasFieldModel.create(
        created_by=user,
        name=oilgas_field.name,
        name_local=oilgas_field.name_local,
        production_start_year=oilgas_field.production_start_year,
        latitude=oilgas_field.latitude,
        longitude=oilgas_field.longitude,
    )
    session.add(model)
    await session.flush()
    await session.refresh(model)
    return OilGasField.model_validate(model)
