"""Performance instrumentation and tracing for the Stitch API.

Two complementary layers:

* Structured-log timing — a SQLAlchemy event listener at the single engine
  chokepoint (:mod:`query_timing`) and a request-timing middleware
  (:mod:`request_logging`), both emitting through :mod:`sinks` to stdout, where
  Azure Container Apps forwards it to Log Analytics. Always on, independent of
  trace sampling.
* OpenTelemetry tracing (:mod:`tracing`) — FastAPI / SQLAlchemy
  auto-instrumentation producing spans, exported over OTLP to a collector or
  logged to stdout (``OTEL_TRACES_EXPORTER``). The request middleware copies the
  request id / scenario onto the active span so the two layers correlate.
"""

from .logging_config import configure_logging
from .query_timing import register_query_timing
from .request_logging import RequestTimingMiddleware
from .tracing import configure_tracing, instrument_fastapi, instrument_sqlalchemy

__all__ = [
    "configure_logging",
    "register_query_timing",
    "RequestTimingMiddleware",
    "configure_tracing",
    "instrument_fastapi",
    "instrument_sqlalchemy",
]
