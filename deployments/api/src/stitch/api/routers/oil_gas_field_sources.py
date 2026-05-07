from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from stitch.ogsi.model import OGFieldSource

from stitch.api.auth import Claims, CurrentUser
from stitch.api.db import og_field_source_actions
from stitch.api.db.config import UnitOfWorkDep
from stitch.api.db.errors import SourceNotFoundError
from stitch.api.entities import (
    OGFieldQueryParams,
    PaginatedResponse,
)
from stitch.api.permissions import licensed_sources

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


@router.get("/")
async def query_oil_gas_field_sources(
    uow: UnitOfWorkDep,
    user: CurrentUser,
    claims: Claims,
    params: Annotated[OGFieldQueryParams, Query()],
) -> PaginatedResponse[OGFieldSource]:
    items, total_count = await og_field_source_actions.query(
        session=uow.session,
        params=params,
        licensed_sources=licensed_sources(claims),
    )
    return PaginatedResponse(
        items=list(items),
        total_count=total_count,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{id}", response_model=OGFieldSource)
async def get_oil_gas_field(
    id: int, uow: UnitOfWorkDep, user: CurrentUser, claims: Claims
):
    try:
        return await og_field_source_actions.get_source(
            session=uow.session,
            id=id,
            licensed_sources=licensed_sources(claims),
        )
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
