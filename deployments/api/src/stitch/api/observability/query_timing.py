"""SQLAlchemy query timing via engine cursor-execute events.

Attaches to the single ``AsyncEngine``'s underlying sync engine (the chokepoint
every query flows through) and times each statement. Slow statements (or all
statements when ``log_all_queries`` is set) are emitted via the query sink;
every statement updates the per-request aggregate in :mod:`context`.

Bound parameter values are intentionally **not** captured — only the
parameterized statement text — to avoid logging PII or large payloads.
"""

import re

from sqlalchemy import event
from sqlalchemy.engine import Engine

from .context import db_stats_var
from .context import request_id_var
from .context import route_var
from .context import scenario_var
from .sinks import emit_query_event

try:  # py3.12+: monotonic, nanosecond resolution
    from time import perf_counter
except ImportError:  # pragma: no cover - perf_counter always present on 3.12
    from time import monotonic as perf_counter

_START_KEY = "_stitch_query_start"
_WHITESPACE = re.compile(r"\s+")


def _normalize_statement(statement: str, max_chars: int) -> str:
    # NB: statements longer than max_chars are truncated to a shared prefix, so
    # queries that differ only past the cutoff (large IN (...) lists, big CTEs)
    # collapse into one group in the analyzer. Acceptable tradeoff; documented in
    # deployments/PERFORMANCE.md so users aren't surprised by merged rows.
    collapsed = _WHITESPACE.sub(" ", statement).strip()
    if len(collapsed) > max_chars:
        return collapsed[:max_chars] + "…"
    return collapsed


def register_query_timing(
    sync_engine: Engine,
    *,
    slow_query_ms: float,
    log_all_queries: bool = False,
    statement_max_chars: int = 2000,
) -> None:
    """Register before/after cursor-execute listeners on ``sync_engine``.

    Pass ``engine.sync_engine`` for an ``AsyncEngine``. Idempotent per engine is
    not guaranteed — call once per engine (``get_engine`` is ``lru_cache``'d, so
    that holds in practice).
    """

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault(_START_KEY, []).append(perf_counter())

    @event.listens_for(sync_engine, "handle_error")
    def _on_error(exc_context):
        # after_cursor_execute does not fire when execution raises, so pop the
        # start time the before-hook pushed; otherwise it leaks and corrupts the
        # timing of the next query on this connection.
        conn = exc_context.connection
        if conn is None:
            return
        start_stack = conn.info.get(_START_KEY)
        if start_stack:
            start_stack.pop()

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        start_stack = conn.info.get(_START_KEY)
        if not start_stack:
            return
        elapsed_ms = (perf_counter() - start_stack.pop()) * 1000.0

        stats = db_stats_var.get()
        if stats is not None:
            stats["count"] += 1
            stats["time_ms"] += elapsed_ms

        if not (log_all_queries or elapsed_ms >= slow_query_ms):
            return

        try:
            rowcount = cursor.rowcount
        except Exception:  # pragma: no cover - driver dependent
            rowcount = None

        emit_query_event(
            {
                "duration_ms": round(elapsed_ms, 2),
                "rowcount": rowcount
                if rowcount is not None and rowcount >= 0
                else None,
                "executemany": executemany,
                "statement": _normalize_statement(statement, statement_max_chars),
                "request_id": request_id_var.get(),
                "route": route_var.get(),
                "scenario": scenario_var.get(),
            }
        )
