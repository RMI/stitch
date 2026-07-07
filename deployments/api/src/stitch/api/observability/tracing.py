"""OpenTelemetry tracing for the API — a thin wrapper over the shared
``stitch.observability`` package (one source of truth across services).

Keeps this module's historical surface (``SERVICE_NAME``,
``configure_tracing(settings)``, ``instrument_fastapi``, ``instrument_sqlalchemy``,
``LoggingSpanExporter``) so call sites (``main.py``, ``db/config.py``) and tests
don't change. The API's query-timing / request-logging / sinks layer stays
API-specific (it hangs off the SQLAlchemy engine).
"""

from typing import TYPE_CHECKING

from stitch.observability import (
    LoggingSpanExporter,
    configure_tracing as _configure_tracing,
    instrument_fastapi,
    instrument_sqlalchemy,
)

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider

    from ..settings import Settings

SERVICE_NAME = "stitch-api"

__all__ = [
    "SERVICE_NAME",
    "LoggingSpanExporter",
    "configure_tracing",
    "instrument_fastapi",
    "instrument_sqlalchemy",
]


def configure_tracing(settings: "Settings") -> "TracerProvider | None":
    """Install the API's global tracer provider, or ``None`` if disabled."""
    return _configure_tracing(
        service_name=SERVICE_NAME,
        enabled=settings.otel_enabled,
        exporter=settings.otel_traces_exporter,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        sample_ratio=settings.otel_sample_ratio,
        # None (not "unknown") when unset, so an env-provided service.version
        # via OTEL_RESOURCE_ATTRIBUTES isn't clobbered by a placeholder.
        version=settings.app_version,
        environment=settings.environment_name,
    )
