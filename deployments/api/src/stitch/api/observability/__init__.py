"""Performance instrumentation and tracing for the Stitch API.

The generic machinery — tracing setup, structured logging, and the
``RequestContextMiddleware`` that establishes per-request context and tags the
active span — lives in the shared ``stitch.observability`` package. This
subpackage holds the API-specific pieces layered on top:

* Structured-log query timing — a SQLAlchemy event listener at the single engine
  chokepoint (:mod:`query_timing`) emitting through :mod:`sinks` to stdout, where
  Azure Container Apps forwards it to Log Analytics. Always on, independent of
  trace sampling.
* Per-request DB aggregates — :mod:`request_logging` extends the shared
  ``RequestContextMiddleware`` to add this request's query count / time to the
  request-summary log event.
* OpenTelemetry tracing (:mod:`tracing`) — a thin wrapper over the shared
  package that pins the API's ``service.name`` and adapts the ``Settings`` object
  to the package's ``configure_tracing`` signature.
"""

from stitch.observability import configure_logging, resource_attributes_from_env
from .query_timing import register_query_timing
from .request_logging import RequestTimingMiddleware
from .tracing import (
    configure_tracing,
    instrument_fastapi,
    instrument_sqlalchemy,
    setup_sqlalchemy_tracing,
)

__all__ = [
    "configure_logging",
    "resource_attributes_from_env",
    "register_query_timing",
    "RequestTimingMiddleware",
    "configure_tracing",
    "instrument_fastapi",
    "instrument_sqlalchemy",
    "setup_sqlalchemy_tracing",
]
