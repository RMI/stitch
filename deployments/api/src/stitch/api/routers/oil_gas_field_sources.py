from __future__ import annotations
from collections.abc import Sequence


from fastapi import APIRouter
from stitch.ogsi.model import OGFieldSource

from stitch.api.auth import CurrentUser
from stitch.api.db import og_field_source_actions
from stitch.api.db.config import UnitOfWorkDep

router = APIRouter(prefix="/oil-gas-field-sources", tags=["oil_gas_field_sources"])


@router.post("/", response_model=OGFieldSource)
async def create_oil_gas_field_source(
    source: OGFieldSource,
    uow: UnitOfWorkDep,
    user: CurrentUser,
) -> OGFieldSource:
    """Create and return a bare Oil & Gas Field Source. Does not create memberships or associated resource.

    Args:
        source: raw source data
        uow: unit of work (db transaction context)
        user: the logged in User

    Returns:
        The OGFieldSource_ object with created id
    """
    session = uow.session

    return await og_field_source_actions.create_source(
        session=session, user=user, source=source
    )


@router.get("/", response_model=Sequence[OGFieldSource])
async def query_oil_gas_field_sources(uow: UnitOfWorkDep):
    # TODO: this **will** need to get paged and/or filtered
    return await og_field_source_actions.list_og_sources(session=uow.session)


@router.get("/{id}", response_model=OGFieldSource)
async def get_oil_gas_field(id: int, uow: UnitOfWorkDep):
    return await og_field_source_actions.get_source(session=uow.session, id=id)
