"""Emission seam for instrumentation events.

Today these functions emit structured log records (the JSON formatter in
:mod:`logging_config` flattens the ``event`` dict into the log line). They are
intentionally the *only* place that decides what happens to a timing event.

OpenTelemetry seam (not built yet, deliberately):
    When we are ready to explore OTel on Azure, the migration is local to this
    module. Either:
      * install ``azure-monitor-opentelemetry`` and rely on the FastAPI /
        SQLAlchemy auto-instrumentors (in which case these sinks stay as the
        lightweight log fallback), or
      * have ``emit_query_event`` / ``emit_request_event`` additionally open a
        span from the timing data already collected here.
    The contextvars in :mod:`context` (request id, route, timing) map directly
    onto span attributes, so no rework of the timing code is required.
"""

import logging

_query_logger = logging.getLogger("stitch.api.observability.query")
_request_logger = logging.getLogger("stitch.api.observability.request")


def emit_query_event(event: dict) -> None:
    """Record a single (slow) database query."""
    _query_logger.info("db_query", extra={"event": event})


def emit_request_event(event: dict) -> None:
    """Record a completed HTTP request with its database aggregates."""
    _request_logger.info("request", extra={"event": event})
