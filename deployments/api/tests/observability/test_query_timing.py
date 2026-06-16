"""Tests for the SQLAlchemy query timing listener."""

import logging

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from stitch.api.observability import query_timing
from stitch.api.observability.context import db_stats_var, new_db_stats
from stitch.api.observability.logging_config import JsonFormatter


@pytest.fixture
async def timed_engine(monkeypatch):
    """Async SQLite engine with timing registered and emitted events captured."""
    captured: list[dict] = []
    monkeypatch.setattr(
        query_timing, "emit_query_event", lambda event: captured.append(event)
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    query_timing.register_query_timing(
        engine.sync_engine, slow_query_ms=0, log_all_queries=True
    )
    yield engine, captured
    await engine.dispose()


class TestQueryTiming:
    @pytest.mark.anyio
    async def test_emits_event_per_query(self, timed_engine):
        engine, captured = timed_engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        assert len(captured) == 1
        event = captured[0]
        assert event["duration_ms"] >= 0
        assert event["statement"] == "SELECT 1"

    @pytest.mark.anyio
    async def test_accumulates_into_request_stats(self, timed_engine):
        engine, _ = timed_engine
        stats = new_db_stats()
        token = db_stats_var.set(stats)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                await conn.execute(text("SELECT 2"))
        finally:
            db_stats_var.reset(token)

        assert stats["count"] == 2
        assert stats["time_ms"] >= 0

    @pytest.mark.anyio
    async def test_respects_slow_query_threshold(self, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            query_timing, "emit_query_event", lambda event: captured.append(event)
        )
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        # Very high threshold and not logging all: trivial query is not emitted.
        query_timing.register_query_timing(
            engine.sync_engine, slow_query_ms=10_000, log_all_queries=False
        )
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        finally:
            await engine.dispose()

        assert captured == []

    def test_normalize_statement_collapses_and_truncates(self):
        collapsed = query_timing._normalize_statement(
            "SELECT\n  a,\n  b\nFROM t", max_chars=2000
        )
        assert collapsed == "SELECT a, b FROM t"

        truncated = query_timing._normalize_statement("x" * 50, max_chars=10)
        assert truncated == "x" * 10 + "…"


class TestJsonFormatter:
    def test_flattens_event_dict(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="stitch.api.observability.query",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="db_query",
            args=(),
            exc_info=None,
        )
        record.event = {"duration_ms": 12.3, "route": "/oil-gas-fields/"}

        import json

        payload = json.loads(formatter.format(record))
        assert payload["msg"] == "db_query"
        assert payload["duration_ms"] == 12.3
        assert payload["route"] == "/oil-gas-fields/"
        assert payload["level"] == "INFO"
