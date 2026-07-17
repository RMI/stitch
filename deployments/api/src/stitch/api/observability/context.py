"""Per-request context shared between the request middleware and the query
timing listener.

The generic request context (request id / route / scenario) is owned by the
shared ``stitch.observability`` middleware and re-exported here, so this module
stays the single import site the query-timing listener reads from. The
``db_stats`` dict is API-specific: the middleware sets it before handing off to
the rest of the app, the SQLAlchemy listener mutates it in place, and the
middleware reads back the aggregated query count / time once the request
completes.
"""

from contextvars import ContextVar
from typing import TypedDict

from stitch.observability.middleware import (
    request_id_var,
    route_var,
    scenario_var,
)

__all__ = [
    "DbStats",
    "db_stats_var",
    "new_db_stats",
    "request_id_var",
    "route_var",
    "scenario_var",
]


class DbStats(TypedDict):
    count: int
    time_ms: float


db_stats_var: ContextVar[DbStats | None] = ContextVar("stitch_db_stats", default=None)


def new_db_stats() -> DbStats:
    return {"count": 0, "time_ms": 0.0}
