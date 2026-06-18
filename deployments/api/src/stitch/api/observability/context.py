"""Per-request context shared between the request middleware and the query
timing listener.

The middleware sets these context variables *before* handing off to the rest
of the app, so the values (and the mutable ``db_stats`` dict) are captured into
the downstream task and visible to the SQLAlchemy listener. The listener
mutates the same ``db_stats`` dict in place, which is how the middleware reads
back the aggregated query count / time once the request completes.
"""

from contextvars import ContextVar
from typing import TypedDict


class DbStats(TypedDict):
    count: int
    time_ms: float


request_id_var: ContextVar[str | None] = ContextVar("stitch_request_id", default=None)
route_var: ContextVar[str | None] = ContextVar("stitch_route", default=None)
db_stats_var: ContextVar[DbStats | None] = ContextVar("stitch_db_stats", default=None)
# Optional caller-supplied experiment label (from the X-Perf-Scenario header).
# Lets a batch of traffic be tagged so query/request events can be compared
# across variants (e.g. data volume, query params) by the analyzer.
scenario_var: ContextVar[str | None] = ContextVar("stitch_scenario", default=None)


def new_db_stats() -> DbStats:
    return {"count": 0, "time_ms": 0.0}
