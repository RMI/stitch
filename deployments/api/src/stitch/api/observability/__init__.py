"""Performance instrumentation for the Stitch API.

The generic machinery — tracing setup, structured logging, and the
``RequestContextMiddleware`` that establishes per-request context and tags the
active span — lives in the shared ``stitch.observability`` package and is wired
up directly in :mod:`stitch.api.main` / :mod:`stitch.api.db.config`. This
subpackage holds the API-specific pieces layered on top:

* Structured-log query timing — a SQLAlchemy event listener at the single engine
  chokepoint (:mod:`query_timing`) emitting through :mod:`sinks` to stdout, where
  Azure Container Apps forwards it to Log Analytics. Always on, independent of
  trace sampling.
* Per-request DB aggregates — :mod:`request_logging` extends the shared
  ``RequestContextMiddleware`` to add this request's query count / time to the
  request-summary log event.
"""

from .query_timing import register_query_timing
from .request_logging import RequestTimingMiddleware

__all__ = [
    "register_query_timing",
    "RequestTimingMiddleware",
]
