# NOTE: deliberately no `from __future__ import annotations` here. The /start
# endpoint is generated with the caller-supplied request model as a real
# annotation object; stringized annotations would break FastAPI's body parsing.

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from starlette.status import HTTP_200_OK, HTTP_202_ACCEPTED, HTTP_404_NOT_FOUND

from .manager import JobManager
from .models import JobRecord

logger = logging.getLogger("stitch.jobs")


def make_job_router(
    manager: JobManager,
    *,
    start_request_model: type[BaseModel],
    result_model: type[BaseModel],
    params_model: type[BaseModel] | None = None,
    to_params: Callable[[Any], BaseModel] | None = None,
    dependencies: Sequence[Any] = (),
    initiated_by: Callable[..., Awaitable[str | None] | str | None] | None = None,
    tags: Sequence[str] | None = None,
    default_list_limit: int = 20,
) -> APIRouter:
    """Build a reusable ``/start`` + ``/status`` + ``/jobs`` router for a job.

    ``start_request_model`` is the POST body; ``result_model`` is what
    ``run_fn`` returns. By default the request body *is* the params; pass
    ``params_model`` + ``to_params`` when the stored params differ from the
    wire request. ``dependencies`` is where the service plugs in its permission
    gate (e.g. ``[Depends(require_permissions(...))]``); ``initiated_by`` is an
    optional dependency returning the caller's display label.
    """
    params_model = params_model or start_request_model
    to_params = to_params or (lambda request: request)
    resolve_initiated_by = initiated_by or (lambda: None)

    record_model = JobRecord[params_model, result_model]  # type: ignore[valid-type]

    router = APIRouter(tags=list(tags) if tags else None)

    @router.post(
        "/start",
        status_code=HTTP_202_ACCEPTED,
        response_model=record_model,
        dependencies=list(dependencies),
    )
    async def start(
        request: start_request_model,  # type: ignore[valid-type]
        response: Response,
        initiated_by_label: Any = Depends(resolve_initiated_by),
    ):
        """Start the job, or join an existing matching run.

        Returns ``202`` with a fresh record, or ``200`` with the existing record
        when a recent/active run with the same dedup key is found (so a second
        caller observes that run rather than starting a duplicate).
        """
        params = to_params(request)
        record, created = await manager.start(params, initiated_by=initiated_by_label)
        if not created:
            response.status_code = HTTP_200_OK
        return record

    @router.get("/status/{job_id}", response_model=record_model)
    async def status(job_id: str):
        record = await manager.get(job_id)
        if record is None:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"No job found with id {job_id}.",
            )
        return record

    @router.get("/jobs", response_model=list[record_model])
    async def jobs(
        limit: int = Query(default=default_list_limit, ge=1, le=200),
    ):
        """List recent jobs, newest first — for discovering an in-flight run."""
        return await manager.list(limit=limit)

    return router
