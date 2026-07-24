"""API-specific per-request DB stats for the query-timing listener.

The generic request context (request id / route / scenario) is owned by the
shared ``stitch.observability.middleware``; consumers import those directly from
there. This module owns only the API-specific ``db_stats`` dict: the request
middleware sets it before handing off to the rest of the app, the SQLAlchemy
listener mutates it in place, and the middleware reads back the aggregated query
count / time once the request completes.
"""

from contextvars import ContextVar
from typing import TypedDict

__all__ = [
    "DbStats",
    "db_stats_var",
    "new_db_stats",
]


class DbStats(TypedDict):
    count: int
    time_ms: float


db_stats_var: ContextVar[DbStats | None] = ContextVar("stitch_db_stats", default=None)


def new_db_stats() -> DbStats:
    return {"count": 0, "time_ms": 0.0}
