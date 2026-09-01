from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from stitch.auth.permissions import SOURCE_READ_PERMISSIONS, SOURCE_WRITE
from stitch.ogsi.model import OGFieldSource, OGFieldSourceView

from stitch.api.auth import (
    Claims,
    CurrentUser,
    require_permissions,
)
from stitch.api.db import og_field_source_actions
from stitch.api.db.config import UnitOfWorkDep
from stitch.api.db.errors import SourceNotFoundError
from stitch.api.entities import (
    OGFieldQueryParams,
    PaginatedResponse,
)
from stitch.api.permissions import licensed_sources

router = APIRouter(prefix="/oil-gas-field-sources", tags=["oil_gas_field_sources"])


@router.post(
    "/",
    response_model=OGFieldSourceView,
    dependencies=[Depends(require_permissions(SOURCE_WRITE))],
    deprecated=True,
)
async def create_oil_gas_field_source(
    source: OGFieldSource,
    uow: UnitOfWorkDep,
    user: CurrentUser,
) -> OGFieldSourceView:
    """Create and return a bare Oil & Gas Field Source. Does not create memberships or associated resource.

    Deprecated: creates a source detached from any resource, which breaks the
    invariant that a source is always attached to at least one resource. Use
    ``POST /oil-gas-fields/{id}/sources`` to create a source and attach it to a
    resource. This route will be removed once STIT-527 lands.

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


@router.get(
    "/",
    dependencies=[Depends(require_permissions(*SOURCE_READ_PERMISSIONS, check="any"))],
)
async def query_oil_gas_field_sources(
    uow: UnitOfWorkDep,
    user: CurrentUser,
    claims: Claims,
    params: Annotated[OGFieldQueryParams, Query()],
) -> PaginatedResponse[OGFieldSourceView]:
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


@router.get(
    "/{id}",
    response_model=OGFieldSourceView,
    dependencies=[Depends(require_permissions(*SOURCE_READ_PERMISSIONS, check="any"))],
)
async def get_oil_gas_field(
    id: int, uow: UnitOfWorkDep, user: CurrentUser, claims: Claims
) -> OGFieldSourceView:
    try:
        return await og_field_source_actions.get_source(
            session=uow.session,
            id=id,
            licensed_sources=licensed_sources(claims),
        )
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get(
    "/{id}/detail",
    dependencies=[Depends(require_permissions(*SOURCE_READ_PERMISSIONS, check="any"))],
)
async def get_oil_gas_field_detail(
    id: int, uow: UnitOfWorkDep, user: CurrentUser, claims: Claims
) -> OGFieldSource:
    try:
        return await og_field_source_actions.get_source_detail(
            session=uow.session,
            id=id,
            licensed_sources=licensed_sources(claims),
        )
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
