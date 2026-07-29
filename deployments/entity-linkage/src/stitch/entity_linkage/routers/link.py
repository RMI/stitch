from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.status import HTTP_502_BAD_GATEWAY
from stitch.auth.permissions import SERVICE_ENTITY_LINKAGE_RUN

from stitch.entity_linkage import matching
from stitch.entity_linkage.auth import AuthContext, require_permissions
from stitch.entity_linkage.client import StitchApiClient
from stitch.entity_linkage.entities import (
    BulkLinkResponse,
    ResourceLinkResult,
    user_label,
)
from stitch.entity_linkage.errors import StitchAPIError

router = APIRouter(tags=["entity-linkage"])


class LinkRequest(BaseModel):
    apply_merges: bool = Field(
        default=False,
        description=(
            "When true, submit the resource's confirmed match group to the "
            "Stitch API as a merge candidate."
        ),
    )


class BulkLinkRequest(BaseModel):
    apply_merges: bool = Field(
        default=False,
        description=(
            "When true, submit each confirmed match group to the Stitch API as "
            "a merge candidate."
        ),
    )
    page_size: int = Field(
        default=200,
        ge=1,
        le=200,
        description="Page size used to stream resources during the pass.",
    )


@router.post(
    "/oil-gas-fields/link",
    response_model=BulkLinkResponse,
    dependencies=[Depends(require_permissions(SERVICE_ENTITY_LINKAGE_RUN))],
)
async def link_all(
    request: BulkLinkRequest,
    auth_context: AuthContext,
) -> BulkLinkResponse:
    """Bounded-memory linkage pass over every resource.

    Streams resources one page at a time and links each against its duplicates,
    replacing the whole-dataset in-memory ``/start`` pass. Still runs
    synchronously in-request: this addresses memory, not wall-time (the queued
    execution model is tracked separately).
    """
    try:
        async with StitchApiClient() as client:
            return await matching.link_all(
                client,
                apply_merges=request.apply_merges,
                page_size=request.page_size,
                initiated_by=user_label(auth_context.user),
            )
    except StitchAPIError as exc:
        raise HTTPException(
            status_code=HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post(
    "/oil-gas-fields/{resource_id}/link",
    response_model=ResourceLinkResult,
    dependencies=[Depends(require_permissions(SERVICE_ENTITY_LINKAGE_RUN))],
)
async def link_one(
    resource_id: int,
    request: LinkRequest,
    auth_context: AuthContext,
) -> ResourceLinkResult:
    """Link a single resource against its duplicates in bounded memory.

    This is the unit of work the bulk pass iterates -- and the natural task a
    future queue would enqueue.
    """
    try:
        async with StitchApiClient() as client:
            return await matching.link_resource(
                client,
                resource_id,
                apply_merges=request.apply_merges,
            )
    except StitchAPIError as exc:
        raise HTTPException(
            status_code=HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
