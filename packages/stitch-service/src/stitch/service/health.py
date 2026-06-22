from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.status import HTTP_200_OK


def format_started_at(value: object) -> str | None:
    """Render an ``app.state.started_at`` value as an ISO-8601 UTC string."""
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return None


def uptime_seconds(value: object) -> float | None:
    if isinstance(value, datetime):
        return round((datetime.now(UTC) - value).total_seconds(), 3)
    return None


def runtime_block(started_at: object) -> dict[str, object]:
    """The ``runtime`` sub-object shared by every service's /health/details."""
    return {
        "started_at": format_started_at(started_at),
        "uptime_seconds": uptime_seconds(started_at),
    }


def make_basic_health_router(service: str) -> APIRouter:
    """A liveness ``GET /health`` returning ``{"service", "status": "ok"}``.

    Readiness/dependency probes belong in a service-specific ``/health/details``
    (they differ per service); compose this for the trivial liveness check.
    """
    router = APIRouter()

    @router.get("/health")
    async def check_health() -> JSONResponse:
        return JSONResponse(
            {"service": service, "status": "ok"}, status_code=HTTP_200_OK
        )

    return router
