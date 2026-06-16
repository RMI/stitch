"""End-to-end test for the request timing middleware.

Exercises the full middleware -> endpoint -> DB path, which is where the
per-request DB aggregation depends on contextvar propagation surviving
BaseHTTPMiddleware's task hand-off and SQLAlchemy's async bridge.
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from stitch.api.observability import RequestTimingMiddleware, register_query_timing
from stitch.api.observability import request_logging


@pytest.fixture
async def instrumented_app(monkeypatch):
    captured: list[dict] = []
    monkeypatch.setattr(
        request_logging, "emit_request_event", lambda event: captured.append(event)
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    register_query_timing(engine.sync_engine, slow_query_ms=0, log_all_queries=True)

    app = FastAPI()
    app.add_middleware(RequestTimingMiddleware)

    @app.get("/things/{thing_id}")
    async def get_thing(thing_id: int):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.execute(text("SELECT 2"))
        return {"id": thing_id}

    @app.get("/no-db")
    async def no_db():
        return {"ok": True}

    yield app, captured
    await engine.dispose()


class TestRequestTimingMiddleware:
    @pytest.mark.anyio
    async def test_emits_summary_with_db_aggregates(self, instrumented_app):
        app, captured = instrumented_app
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/things/42")

        assert response.status_code == 200
        assert response.headers["X-Request-ID"]

        assert len(captured) == 1
        event = captured[0]
        assert event["method"] == "GET"
        assert event["route"] == "/things/{thing_id}"
        assert event["status_code"] == 200
        assert event["db_query_count"] == 2
        assert event["duration_ms"] >= 0
        assert event["db_time_ms"] >= 0

    @pytest.mark.anyio
    async def test_route_without_db_has_zero_queries(self, instrumented_app):
        app, captured = instrumented_app
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get("/no-db")

        assert captured[-1]["route"] == "/no-db"
        assert captured[-1]["db_query_count"] == 0
