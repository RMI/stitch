from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.status import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE

from stitch.client import StitchAPIError

from stitch.entity_linkage.client import StitchApiClient
from stitch.entity_linkage.settings import get_settings


router = APIRouter()


def _format_started_at(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return None


def _uptime_seconds(value: object) -> float | None:
    if isinstance(value, datetime):
        return round((datetime.now(UTC) - value).total_seconds(), 3)
    return None


@router.get("/health")
async def check_health():
    return JSONResponse(
        {"service": "entity_linkage", "status": "ok"}, status_code=HTTP_200_OK
    )


@router.get("/health/details")
async def check_health_details(request: Request):
    settings = get_settings()
    started_at = getattr(request.app.state, "started_at", None)
    auth_config_validated = bool(
        getattr(request.app.state, "auth_config_validated", False)
    )
    downstream_auth_config_validated = bool(
        getattr(request.app.state, "downstream_auth_config_validated", False)
    )

    downstream: dict[str, object] = {
        "target": f"{str(settings.api_base_url).rstrip('/')}/auth/me",
        "auth_mode": "env_bearer_token",
        "startup_validated": downstream_auth_config_validated,
        "api_reachable": False,
        "token_accepted": False,
        "ready": False,
    }
    status = "ok"
    ready = True
    status_code = HTTP_200_OK

    try:
        async with StitchApiClient() as client:
            auth_me = await client.get_auth_me()
        downstream["api_reachable"] = True
        downstream["token_accepted"] = True
        downstream["ready"] = True
        claims = auth_me.get("claims")
        if isinstance(claims, dict):
            downstream["subject"] = claims.get("sub")
    except (StitchAPIError, ValueError) as exc:
        status = "degraded"
        ready = False
        status_code = HTTP_503_SERVICE_UNAVAILABLE
        downstream["error"] = str(exc)
        if isinstance(exc, StitchAPIError):
            downstream["api_reachable"] = exc.status_code != 401

    payload = {
        "status": status,
        "ready": ready,
        "service": "entity-linkage",
        "runtime": {
            "started_at": _format_started_at(started_at),
            "uptime_seconds": _uptime_seconds(started_at),
        },
        "auth": {
            "disabled": settings.auth_disabled,
            "startup_validated": auth_config_validated,
        },
        "frontend": {
            "origin": str(settings.frontend_origin_url),
        },
        "downstream_api": downstream,
    }

    return JSONResponse(payload, status_code=status_code)
