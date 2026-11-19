from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from stitch.ogsi.model import OGFieldSource, OGFieldSourceView

from stitch.api.auth import (
    SOURCE_READ_ANY,
    SOURCE_WRITE,
    AuthenticatedUser,
    licensed_sources,
    require_user,
)
from stitch.api.db import og_field_source_actions
from stitch.api.db.config import UnitOfWorkDep
from stitch.api.db.errors import SourceNotFoundError
from stitch.api.entities import (
    OGFieldQueryParams,
    PaginatedResponse,
)

router = APIRouter(prefix="/oil-gas-field-sources", tags=["oil_gas_field_sources"])


@router.post(
    "/",
    response_model=OGFieldSourceView,
    deprecated=True,
)
async def create_oil_gas_field_source(
    source: OGFieldSource,
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user(SOURCE_WRITE))],
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
)
async def query_oil_gas_field_sources(
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user(SOURCE_READ_ANY))],
    params: Annotated[OGFieldQueryParams, Query()],
) -> PaginatedResponse[OGFieldSourceView]:
    items, total_count = await og_field_source_actions.query(
        session=uow.session,
        params=params,
        licensed_sources=licensed_sources(user.claims),
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
)
async def get_oil_gas_field(
    id: int,
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user(SOURCE_READ_ANY))],
) -> OGFieldSourceView:
    try:
        return await og_field_source_actions.get_source(
            session=uow.session,
            id=id,
            licensed_sources=licensed_sources(user.claims),
        )
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get(
    "/{id}/detail",
)
async def get_oil_gas_field_detail(
    id: int,
    uow: UnitOfWorkDep,
    user: Annotated[AuthenticatedUser, Depends(require_user(SOURCE_READ_ANY))],
) -> OGFieldSource:
    try:
        return await og_field_source_actions.get_source_detail(
            session=uow.session,
            id=id,
            licensed_sources=licensed_sources(user.claims),
        )
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
