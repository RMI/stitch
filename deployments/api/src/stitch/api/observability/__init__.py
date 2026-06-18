"""Lightweight performance instrumentation for the Stitch API.

Captures per-query and per-request timing and emits it as structured logs to
stdout, where Azure Container Apps forwards it to Log Analytics for querying.

The instrumentation is deliberately small: a SQLAlchemy event listener at the
single engine chokepoint (:mod:`query_timing`) and a request-timing middleware
(:mod:`request_logging`). All emission flows through :mod:`sinks`, which is the
seam where OpenTelemetry spans can later be added without touching the timing
code (see that module's docstring).
"""

from .logging_config import configure_logging
from .query_timing import register_query_timing
from .request_logging import RequestTimingMiddleware

__all__ = [
    "configure_logging",
    "register_query_timing",
    "RequestTimingMiddleware",
]
