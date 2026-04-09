from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.status import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE

from stitch.api.build_info import get_build_info
from stitch.api.db.config import EngineDep
from stitch.api.settings import SettingsDep

router = APIRouter()


def _format_started_at(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return None


def _uptime_seconds(value: object) -> float | None:
    if isinstance(value, datetime):
        return round((datetime.now(UTC) - value).total_seconds(), 3)
    return None


def _database_target(settings: SettingsDep) -> dict[str, str | int | None]:
    url = settings.get_database_url()

    if settings.dialect == "sqlite":
        return {
            "dialect": settings.dialect,
            "database": url.database,
        }

    return {
        "dialect": settings.dialect,
        "host": url.host,
        "port": url.port,
        "database": url.database,
    }


@router.get("/health")
async def check_health():
    return JSONResponse({"status": "ok"}, status_code=HTTP_200_OK)


@router.get("/health/details")
async def check_health_details(
    request: Request,
    settings: SettingsDep,
    engine: EngineDep,
):
    started_at = getattr(request.app.state, "started_at", None)
    auth_config_validated = bool(
        getattr(request.app.state, "auth_config_validated", False)
    )

    local_build = get_build_info()

    db_status: dict[str, object] = {
        **_database_target(settings),
        "reachable": False,
    }

    status_code = HTTP_200_OK
    overall_status = "ok"

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        db_status["reachable"] = True
    except SQLAlchemyError as exc:
        overall_status = "degraded"
        status_code = HTTP_503_SERVICE_UNAVAILABLE
        db_status["error"] = exc.__class__.__name__

    payload = {
        "status": overall_status,
        "service": "stitch-api",
        "runtime": {
            "environment": settings.environment,
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
        "database": db_status,
        "build": {
            "app_version": settings.app_version or local_build.app_version,
            "build_id": settings.build_id or local_build.build_id,
            "git_sha": settings.git_sha or local_build.git_sha,
            "build_time": settings.build_time or local_build.build_time,
        },
    }

    return JSONResponse(payload, status_code=status_code)
