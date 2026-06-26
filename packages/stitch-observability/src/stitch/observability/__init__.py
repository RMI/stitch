"""Shared OpenTelemetry tracing for Stitch services.

`configure_tracing` builds the global provider (parametrized by ``service_name``);
`instrument_fastapi` / `instrument_httpx` / `instrument_sqlalchemy` auto-instrument
the relevant layers. httpx instrumentation is what propagates the W3C
``traceparent`` so a service's downstream calls join the same trace end-to-end.
"""

from .settings import OTelSettings
from .tracing import (
    LoggingSpanExporter,
    configure_tracing,
    get_tracer,
    instrument_fastapi,
    instrument_httpx,
    instrument_sqlalchemy,
    shutdown_tracing,
)

__all__ = [
    "LoggingSpanExporter",
    "OTelSettings",
    "configure_tracing",
    "get_tracer",
    "instrument_fastapi",
    "instrument_httpx",
    "instrument_sqlalchemy",
    "shutdown_tracing",
]
