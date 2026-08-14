from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.status import (
    HTTP_202_ACCEPTED,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_502_BAD_GATEWAY,
)
from stitch.auth.permissions import SERVICE_ENTITY_LINKAGE_RUN

from stitch.entity_linkage import matching
from stitch.entity_linkage.auth import AuthContext, require_permissions
from stitch.entity_linkage.client import StitchApiClient
from stitch.entity_linkage.entities import (
    BulkLinkResponse,
    LinkProgress,
    ResourceLinkResult,
    user_label,
)
from stitch.entity_linkage.errors import StitchAPIError
from stitch.entity_linkage.jobs import (
    JobAlreadyRunningError,
    JobRecord,
    JobState,
    get_job_manager,
)

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


class LinkAllStartResponse(BaseModel):
    job_id: str
    state: JobState
    started_at: datetime
    initiated_by: str


@router.post(
    "/oil-gas-fields/link",
    status_code=HTTP_202_ACCEPTED,
    response_model=LinkAllStartResponse,
    dependencies=[Depends(require_permissions(SERVICE_ENTITY_LINKAGE_RUN))],
)
async def start_link_all(
    request: BulkLinkRequest,
    auth_context: AuthContext,
) -> LinkAllStartResponse:
    """Launch a full linkage pass in the background. Poll GET /oil-gas-fields/link/status.

    Streams resources one page at a time and links each against its duplicates,
    replacing the whole-dataset in-memory ``/start`` pass. Running as a background
    job keeps the pass non-blocking and pollable at production scale; downstream
    failures are captured on the job record rather than surfaced here.
    """
    initiated_by = user_label(auth_context.user)
    # One object, shared between the run body and the job record, so the status
    # endpoint reports live counters instead of only "running".
    progress = LinkProgress()

    async def run() -> BulkLinkResponse:
        async with StitchApiClient() as client:
            return await matching.link_all(
                client,
                apply_merges=request.apply_merges,
                page_size=request.page_size,
                initiated_by=initiated_by,
                progress=progress,
            )

    try:
        record = await get_job_manager().start(request, run, progress=progress)
    except JobAlreadyRunningError as exc:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return LinkAllStartResponse(
        job_id=record.job_id,
        state=record.state,
        started_at=record.started_at,
        initiated_by=initiated_by,
    )


@router.get(
    "/oil-gas-fields/link/status",
    response_model=JobRecord,
    dependencies=[Depends(require_permissions(SERVICE_ENTITY_LINKAGE_RUN))],
)
async def link_all_status() -> JobRecord:
    """Return the most recent linkage pass's state and result."""
    record = get_job_manager().current()
    if record is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="No linkage run has been started yet.",
        )
    return record


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
        # A 404 from the downstream API means the resource doesn't exist; surface
        # that as 404 rather than a generic bad-gateway. Any other downstream
        # failure is an upstream problem -> 502.
        status_code = (
            HTTP_404_NOT_FOUND
            if exc.status_code == HTTP_404_NOT_FOUND
            else HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
