"""Emission seam for the API's query-timing events.

Emits a structured log record (the shared ``stitch.observability`` JSON
formatter flattens the ``event`` dict into the log line), intentionally the *only* place
that decides what happens to a query event. Per-request summaries are emitted by
the shared ``RequestContextMiddleware`` (which the API's ``RequestTimingMiddleware``
extends with the DB aggregates), not here.

Relationship to OpenTelemetry:
    Tracing is wired up via the shared ``stitch.observability`` package
    (``setup_fastapi_tracing`` in :mod:`stitch.api.main`, ``setup_sqlalchemy_tracing``
    in :mod:`stitch.api.db.config`), which auto-instruments FastAPI / SQLAlchemy;
    spans are exported over OTLP to a collector or logged to stdout, depending on
    ``OTEL_TRACES_EXPORTER``. This sink is the lightweight structured-log path and
    runs *independently of trace sampling* — so a slow query is still logged even
    when its trace is dropped.
"""

import logging

_query_logger = logging.getLogger("stitch.api.observability.query")


def emit_query_event(event: dict) -> None:
    """Record a single (slow) database query."""
    _query_logger.info("db_query", extra={"event": event})
