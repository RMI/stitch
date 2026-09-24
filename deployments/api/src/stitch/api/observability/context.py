"""API-specific per-request DB stats and query labels for the timing listener.

The generic request context (request id / route / scenario) is owned by the
shared ``stitch.observability.middleware``; consumers import those directly from
there. This module owns the API-specific pieces the query-timing listener reads:
the ``db_stats`` dict (the request middleware sets it before handing off to the
rest of the app, the SQLAlchemy listener mutates it in place, and the middleware
reads back the aggregated query count / time once the request completes) and the
optional ``query_name`` label a call site attaches to the queries it runs.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TypedDict

__all__ = [
    "DbStats",
    "db_stats_var",
    "named_query",
    "new_db_stats",
    "query_name_var",
]


class DbStats(TypedDict):
    count: int
    time_ms: float


db_stats_var: ContextVar[DbStats | None] = ContextVar("stitch_db_stats", default=None)

# Optional label a call site attaches to the queries it runs, so the timing
# listener can tag its events with a stable ``query_name`` instead of relying on
# SQL-text matching. Defaults to ``None`` (unlabeled), and every statement run
# inside a ``named_query`` scope -- including ORM-emitted secondary queries and
# shared helpers -- inherits the active name.
query_name_var: ContextVar[str | None] = ContextVar("stitch_query_name", default=None)


def new_db_stats() -> DbStats:
    return {"count": 0, "time_ms": 0.0}


@contextmanager
def named_query(name: str) -> Iterator[None]:
    """Label every DB query run within this scope with ``name``.

    Set at a logical-operation boundary (typically a DB action function). The
    label is read by the query-timing listener and added to its emitted events;
    it resets on exit so nothing leaks to later queries.
    """
    token = query_name_var.set(name)
    try:
        yield
    finally:
        query_name_var.reset(token)
