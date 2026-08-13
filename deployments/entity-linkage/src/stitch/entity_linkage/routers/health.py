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


def _downstream_error_fields(
    exc: StitchAPIError | ValueError,
) -> dict[str, object]:
    if isinstance(exc, ValueError):
        return {
            "has_error": True,
            "error_code": "missing_token",
        }

    status_code = exc.status_code
    if status_code == 401:
        error_code = "downstream_401"
    elif status_code is None:
        error_code = "downstream_error"
    elif status_code >= 500:
        error_code = "downstream_5xx"
    else:
        error_code = "downstream_http_error"

    return {
        "has_error": True,
        "error_code": error_code,
        "http_status": status_code,
    }


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
        "auth_mode": "env_bearer_token",
        "startup_validated": downstream_auth_config_validated,
        "api_reachable": False,
        "token_accepted": False,
        "ready": False,
        "has_error": False,
        "error_code": None,
        "http_status": None,
    }
    status = "ok"
    ready = True
    status_code = HTTP_200_OK

    try:
        # Not batch-tagged: this is a reachability check, and tagging it would let
        # the API's batch-yield gate delay the probe whenever a human is using the
        # app — reporting the API as slow precisely when it is healthy and busy.
        async with StitchApiClient(tag_as_batch=False) as client:
            await client.get_auth_me()
        downstream["api_reachable"] = True
        downstream["token_accepted"] = True
        downstream["ready"] = True
    except (StitchAPIError, ValueError) as exc:
        status = "degraded"
        ready = False
        status_code = HTTP_503_SERVICE_UNAVAILABLE
        downstream.update(_downstream_error_fields(exc))
        if isinstance(exc, StitchAPIError):
            downstream["api_reachable"] = exc.status_code is not None
            downstream["token_accepted"] = (
                exc.status_code is not None and exc.status_code != 401
            )

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
