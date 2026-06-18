"""Per-request timing middleware.

Establishes the per-request context (request id + mutable DB-stats dict)
*before* delegating downstream, so the query timing listener accumulates into
the same dict. On completion it emits a single request summary including the
aggregated database query count and time.
"""

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match

from .context import db_stats_var
from .context import new_db_stats
from .context import request_id_var
from .context import route_var
from .context import scenario_var
from .sinks import emit_request_event
from .query_timing import perf_counter

_REQUEST_ID_HEADER = "X-Request-ID"
_SCENARIO_HEADER = "X-Perf-Scenario"
_SCENARIO_MAX_CHARS = 80


def _route_template(request: Request) -> str:
    """Return the matched route template (e.g. ``/oil-gas-fields/{id}``).

    Re-runs route matching against the app's routes — ``scope["route"]`` is not
    reliably populated across Starlette versions. Falls back to the raw path so
    we never lose the event, accepting higher cardinality in that case.
    """
    for route in request.app.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            return getattr(route, "path", request.url.path)
    return request.url.path


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = uuid4().hex
        # Route matching uses scope path/method, both available pre-dispatch, so
        # query events emitted during the request can carry the route too.
        route = _route_template(request)
        scenario = request.headers.get(_SCENARIO_HEADER)
        if scenario:
            scenario = scenario[:_SCENARIO_MAX_CHARS]
        stats = new_db_stats()
        id_token = request_id_var.set(request_id)
        stats_token = db_stats_var.set(stats)
        route_token = route_var.set(route)
        scenario_token = scenario_var.set(scenario)

        start = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[_REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = (perf_counter() - start) * 1000.0
            emit_request_event(
                {
                    "request_id": request_id,
                    "method": request.method,
                    "route": route,
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 2),
                    "db_query_count": stats["count"],
                    "db_time_ms": round(stats["time_ms"], 2),
                    "scenario": scenario,
                }
            )
            request_id_var.reset(id_token)
            db_stats_var.reset(stats_token)
            route_var.reset(route_token)
            scenario_var.reset(scenario_token)
