"""End-to-end test for the request timing middleware.

Exercises the full middleware -> endpoint -> DB path, which is where the
per-request DB aggregation depends on contextvar propagation surviving
BaseHTTPMiddleware's task hand-off and SQLAlchemy's async bridge. The generic
request-summary log is emitted by the shared ``RequestContextMiddleware`` under
the ``stitch.observability.request`` logger (captured via caplog); the API
subclass grafts on the ``db_query_count`` / ``db_time_ms`` fields.
"""

import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from stitch.api.observability import RequestTimingMiddleware, register_query_timing
from stitch.api.observability import query_timing

_REQUEST_LOGGER = "stitch.observability.request"
_SCENARIO_HEADER = "X-Stitch-Perf-Scenario"


def _request_events(caplog) -> list[dict]:
    return [r.event for r in caplog.records if r.name == _REQUEST_LOGGER]


@pytest.fixture
async def instrumented_app(monkeypatch):
    captured_queries: list[dict] = []
    monkeypatch.setattr(
        query_timing, "emit_query_event", lambda event: captured_queries.append(event)
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

    yield app, captured_queries
    await engine.dispose()


class TestRequestTimingMiddleware:
    @pytest.mark.anyio
    async def test_emits_summary_with_db_aggregates(self, instrumented_app, caplog):
        app, _ = instrumented_app
        with caplog.at_level(logging.INFO, logger=_REQUEST_LOGGER):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/things/42")

        assert response.status_code == 200
        assert response.headers["X-Request-ID"]

        events = _request_events(caplog)
        assert len(events) == 1
        event = events[0]
        assert event["method"] == "GET"
        assert event["route"] == "/things/{thing_id}"
        assert event["status_code"] == 200
        assert event["db_query_count"] == 2
        assert event["duration_ms"] >= 0
        assert event["db_time_ms"] >= 0
        assert event["scenario"] is None

    @pytest.mark.anyio
    async def test_route_without_db_has_zero_queries(self, instrumented_app, caplog):
        app, _ = instrumented_app
        with caplog.at_level(logging.INFO, logger=_REQUEST_LOGGER):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.get("/no-db")

        event = _request_events(caplog)[-1]
        assert event["route"] == "/no-db"
        assert event["db_query_count"] == 0

    @pytest.mark.anyio
    async def test_scenario_header_tags_request_and_query_events(
        self, instrumented_app, caplog
    ):
        app, captured_queries = instrumented_app
        with caplog.at_level(logging.INFO, logger=_REQUEST_LOGGER):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.get("/things/42", headers={_SCENARIO_HEADER: "vol=50k"})

        assert _request_events(caplog)[-1]["scenario"] == "vol=50k"
        # The label propagates from the middleware to the query listener.
        assert captured_queries, "expected query events to be captured"
        assert all(q["scenario"] == "vol=50k" for q in captured_queries)

    @pytest.mark.anyio
    async def test_scenario_header_is_truncated(self, instrumented_app, caplog):
        app, _ = instrumented_app
        with caplog.at_level(logging.INFO, logger=_REQUEST_LOGGER):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.get("/no-db", headers={_SCENARIO_HEADER: "x" * 200})

        assert len(_request_events(caplog)[-1]["scenario"]) == 80
