"""Shared per-request context + logging middleware for Stitch services.

``RequestContextMiddleware`` establishes a per-request context (a generated
``request_id`` plus an optional caller-supplied scenario label and the matched
route), tags the active OpenTelemetry span with it, and emits one structured
``request`` log record per request — so every service has consistent request
correlation in its logs, an ``X-Request-ID`` response header, and a per-request
summary independent of trace sampling.

It is deliberately DB-agnostic. A service that needs extra per-request data in
the summary (e.g. the API's aggregated DB query count/time) subclasses it and
overrides the ``on_request_start`` / ``request_log_fields`` / ``on_request_finish``
hooks rather than reimplementing the request-id / span / logging plumbing.
"""

from contextvars import ContextVar
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

import logging

from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

_request_logger = logging.getLogger("stitch.observability.request")

_REQUEST_ID_HEADER = "X-Request-ID"
_SCENARIO_HEADER = "X-Perf-Scenario"
_SCENARIO_MAX_CHARS = 80

# Per-request context, set before the request is handled so downstream code
# (and other instrumentation) can read it. Generic across services; DB-specific
# state lives with the service that owns it.
request_id_var: ContextVar[str | None] = ContextVar("stitch_request_id", default=None)
route_var: ContextVar[str | None] = ContextVar("stitch_route", default=None)
# Optional caller-supplied experiment label (from the X-Perf-Scenario header),
# so a batch of traffic can be tagged and compared across variants.
scenario_var: ContextVar[str | None] = ContextVar("stitch_scenario", default=None)


def _route_template(request: "Request") -> str:
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


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Establish per-request context, tag the active span, and log a summary.

    Add it *last* (outermost) so it times the full request, including any inner
    middleware. Subclass hooks let a service add data to the summary without
    touching the request-id / span / logging plumbing.
    """

    def on_request_start(self, request: "Request") -> object:
        """Hook: establish extra per-request context before the request runs.

        Returns opaque state passed to ``request_log_fields`` / ``on_request_finish``.
        """
        return None

    def request_log_fields(self, state: object) -> dict:
        """Hook: extra fields to merge into the request-summary log event."""
        return {}

    def on_request_finish(self, state: object) -> None:
        """Hook: tear down any context established in ``on_request_start``."""

    async def dispatch(self, request: "Request", call_next) -> "Response":
        request_id = uuid4().hex
        # Route matching uses scope path/method, available pre-dispatch, so
        # events emitted during the request can carry the route too.
        route = _route_template(request)
        scenario = request.headers.get(_SCENARIO_HEADER)
        if scenario:
            scenario = scenario[:_SCENARIO_MAX_CHARS]

        id_token = request_id_var.set(request_id)
        route_token = route_var.set(route)
        scenario_token = scenario_var.set(scenario)
        state = self.on_request_start(request)

        # Surface the same context on the active server span (created by the
        # FastAPI instrumentation). No-op when tracing is disabled — the current
        # span is then non-recording.
        span = trace.get_current_span()
        span.set_attribute("stitch.request_id", request_id)
        if scenario:
            span.set_attribute("stitch.scenario", scenario)

        start = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[_REQUEST_ID_HEADER] = request_id
            return response
        finally:
            event = {
                "request_id": request_id,
                "method": request.method,
                "route": route,
                "status_code": status_code,
                "duration_ms": round((perf_counter() - start) * 1000.0, 2),
                "scenario": scenario,
            }
            event.update(self.request_log_fields(state))
            _request_logger.info("request", extra={"event": event})
            self.on_request_finish(state)
            request_id_var.reset(id_token)
            route_var.reset(route_token)
            scenario_var.reset(scenario_token)
