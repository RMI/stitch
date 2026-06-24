"""Emission seam for instrumentation events.

These functions emit structured log records (the JSON formatter in
:mod:`logging_config` flattens the ``event`` dict into the log line). They are
intentionally the *only* place that decides what happens to a timing event.

Relationship to OpenTelemetry:
    Tracing is wired up in :mod:`tracing` via FastAPI / SQLAlchemy
    auto-instrumentation; spans are exported over OTLP to a collector or logged
    to stdout, depending on ``OTEL_TRACES_EXPORTER``. These sinks are kept as
    the lightweight structured-log path and run *independently of trace
    sampling* — so a slow query is still logged even when its trace is dropped.
    The request middleware copies the request id and scenario onto the active
    span, so logs and traces correlate (the route is already present as the
    instrumentation's ``http.route`` attribute).
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
