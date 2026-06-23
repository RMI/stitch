# NOTE: deliberately no `from __future__ import annotations` here. The /start
# endpoint is generated with the caller-supplied request model as a real
# annotation object; stringized annotations would break FastAPI's body parsing.

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, create_model
from starlette.status import HTTP_200_OK, HTTP_202_ACCEPTED, HTTP_404_NOT_FOUND

from .manager import JobManager
from .models import JobRecord

logger = logging.getLogger("stitch.jobs")


def make_job_router(
    manager: JobManager,
    *,
    params_model: type[BaseModel],
    result_model: type[BaseModel],
    force: bool = True,
    dependencies: Sequence[Any] = (),
    initiated_by: Callable[..., Awaitable[str | None] | str | None] | None = None,
    tags: Sequence[str] | None = None,
    default_list_limit: int = 20,
) -> APIRouter:
    """Build a reusable ``/start`` + ``/status`` + ``/jobs`` + ``/find`` router.

    ``params_model`` is the request body *and* the dedup params; ``result_model``
    is what ``run_fn`` returns. ``dependencies`` is where the service plugs in
    its permission gate (e.g. ``[Depends(require_permissions(...))]``);
    ``initiated_by`` is an optional dependency returning the caller's label.

    When ``force`` is true (default) the request body gains a ``force: bool``
    field; setting it bypasses dedup and starts a fresh run. The router strips
    ``force`` before computing the dedup key, so it can never pollute that key —
    services get force without re-deriving the wrapper/strip boilerplate.
    """
    resolve_initiated_by = initiated_by or (lambda: None)
    record_model = JobRecord[params_model, result_model]

    if force:
        # Synthesize "<Params> + force" so callers send/declare just the params.
        request_model = create_model(
            f"{params_model.__name__}StartRequest",
            __base__=params_model,
            force=(
                bool,
                Field(
                    default=False,
                    description="Re-run even if a matching recent run exists.",
                ),
            ),
        )

        def to_params(request: BaseModel) -> BaseModel:
            return params_model(**request.model_dump(exclude={"force"}))

        def extract_force(request: BaseModel) -> bool:
            return bool(getattr(request, "force", False))
    else:
        request_model = params_model

        def to_params(request: BaseModel) -> BaseModel:
            return request

        def extract_force(request: BaseModel) -> bool:
            return False

    router = APIRouter(tags=list(tags) if tags else None)

    @router.post(
        "/start",
        status_code=HTTP_202_ACCEPTED,
        response_model=record_model,
        dependencies=list(dependencies),
    )
    async def start(
        request: request_model,
        response: Response,
        initiated_by_label: Any = Depends(resolve_initiated_by),
    ):
        """Start the job, or join an existing matching run.

        Returns ``202`` with a fresh record, or ``200`` with the existing record
        when a recent/active run with the same dedup key is found (so a second
        caller observes that run rather than starting a duplicate).
        """
        record, created = await manager.start(
            to_params(request),
            initiated_by=initiated_by_label,
            force=extract_force(request),
        )
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

    @router.post("/find", response_model=list[record_model])
    async def find(request: request_model):
        """Return the runs matching a request's params (same dedup policy as
        ``/start``), newest first — so a caller can discover/reuse the existing
        run for exactly these params without scanning the whole job list.
        """
        return await manager.list_for_params(
            to_params(request), limit=default_list_limit
        )

    return router
