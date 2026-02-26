from collections.abc import Sequence
from fastapi import APIRouter

from stitch.api.auth import CurrentUser
from stitch.api.db.config import UnitOfWorkDep
from stitch.api.entities import CreateOilGasField, OilGasField
from stitch.api.db import oilgas_field_actions

router = APIRouter(
    prefix="/oilgasfields",
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_all_oilgas_fields(
    *, uow: UnitOfWorkDep, user: CurrentUser
) -> Sequence[OilGasField]:
    return await oilgas_field_actions.get_all(session=uow.session)


@router.get("/{id}", response_model=OilGasField)
async def get_oilgas_field(
    *, uow: UnitOfWorkDep, user: CurrentUser, id: int
) -> OilGasField:
    return await oilgas_field_actions.get(session=uow.session, id=id)


@router.post("/", response_model=OilGasField)
async def create_oilgas_field(
    *, uow: UnitOfWorkDep, user: CurrentUser, oilgas_field_in: CreateOilGasField
) -> OilGasField:
    return await oilgas_field_actions.create(
        session=uow.session,
        user=user,
        oilgas_field=oilgas_field_in,
    )
