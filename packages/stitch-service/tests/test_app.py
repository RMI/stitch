from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient

from stitch.service import create_app, make_basic_health_router, runtime_block


def test_create_app_mounts_routers_under_prefix_and_runs_startup() -> None:
    events: list[str] = []

    router = APIRouter()

    @router.get("/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "ok"}

    def on_startup(app) -> None:
        events.append("startup")
        app.state.ready = True

    app = create_app(
        routers=[router, make_basic_health_router("svc")],
        cors_origins=["http://localhost:3000/"],
        on_startup=on_startup,
    )

    with TestClient(app) as client:
        assert client.get("/api/v1/ping").json() == {"pong": "ok"}
        health = client.get("/api/v1/health").json()
        assert health == {"service": "svc", "status": "ok"}

    assert events == ["startup"]
    assert app.state.ready is True
    assert app.state.started_at is not None


def test_async_startup_hook_is_awaited() -> None:
    events: list[str] = []

    async def on_startup(app) -> None:
        events.append("async-startup")

    app = create_app(on_startup=on_startup)
    with TestClient(app):
        pass
    assert events == ["async-startup"]


def test_runtime_block_shape() -> None:
    block = runtime_block(None)
    assert block == {"started_at": None, "uptime_seconds": None}
