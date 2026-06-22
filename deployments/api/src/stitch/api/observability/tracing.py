"""OpenTelemetry tracing setup for the API.

Span *generation* is handled by auto-instrumentation (FastAPI + SQLAlchemy);
this module owns span *export*, which is configurable:

* ``console`` (default) — finished spans are emitted as structured log records
  through the existing :class:`JsonFormatter` (see :mod:`logging_config`), so
  local dev gets full trace data on stdout **without** running the collector /
  Jaeger sidecars. This is the "log what OTel would send" path.
* ``otlp`` — spans are shipped via OTLP/gRPC to the collector (``→`` Jaeger).
* ``none`` — tracing is disabled entirely.

Sampling uses ``ParentBased(root=TraceIdRatioBased(ratio))`` so the API honors
an upstream caller's sampling decision (propagated via the W3C ``traceparent``
header) and only samples independently when it is the root of a trace. The
ratio defaults to 1.0 (capture everything) for local dev.
"""

import logging
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fastapi import FastAPI
    from opentelemetry.sdk.trace import ReadableSpan
    from sqlalchemy.engine import Engine

    from ..settings import Settings

SERVICE_NAME = "stitch-api"

_span_logger = logging.getLogger("stitch.api.observability.trace")


class LoggingSpanExporter(SpanExporter):
    """Export finished spans as structured log records instead of shipping them
    to a collector.

    Each span becomes one ``stitch.api.observability.trace`` log record whose
    ``event`` dict the :class:`JsonFormatter` flattens to the top level, so
    fields like ``trace_id`` / ``duration_ms`` are directly queryable and sit
    alongside the request / query events on the same stdout stream.
    """

    def export(self, spans: "Sequence[ReadableSpan]") -> SpanExportResult:
        for span in spans:
            ctx = span.get_span_context()
            parent = span.parent
            duration_ms = (
                round((span.end_time - span.start_time) / 1e6, 2)
                if span.end_time is not None and span.start_time is not None
                else None
            )
            _span_logger.info(
                "span",
                extra={
                    "event": {
                        "span_name": span.name,
                        "trace_id": format(ctx.trace_id, "032x"),
                        "span_id": format(ctx.span_id, "016x"),
                        "parent_span_id": format(parent.span_id, "016x")
                        if parent is not None
                        else None,
                        "kind": span.kind.name,
                        "duration_ms": duration_ms,
                        "status": span.status.status_code.name,
                        "attributes": dict(span.attributes or {}),
                    }
                },
            )
        return SpanExportResult.SUCCESS

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


def configure_tracing(settings: "Settings") -> TracerProvider | None:
    """Install the global tracer provider, or return ``None`` if disabled.

    Call once at startup, before the first span is created. Idempotency is not
    guaranteed — ``set_tracer_provider`` warns if called twice.
    """
    if not settings.otel_enabled or settings.otel_traces_exporter == "none":
        return None

    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.version": settings.app_version or "unknown",
            "deployment.environment": settings.environment_name,
        }
    )
    sampler = ParentBased(root=TraceIdRatioBased(settings.otel_sample_ratio))
    provider = TracerProvider(resource=resource, sampler=sampler)

    if settings.otel_traces_exporter == "otlp":
        # endpoint=None lets the exporter fall back to OTEL_EXPORTER_OTLP_ENDPOINT
        # / the localhost default.
        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:  # "console" — log spans to stdout, no sidecar required.
        provider.add_span_processor(SimpleSpanProcessor(LoggingSpanExporter()))

    trace.set_tracer_provider(provider)
    return provider


def instrument_fastapi(app: "FastAPI") -> None:
    """Auto-instrument the FastAPI app (server spans + traceparent extraction)."""
    FastAPIInstrumentor.instrument_app(app)


def instrument_sqlalchemy(engine: "Engine") -> None:
    """Auto-instrument a (sync) SQLAlchemy engine for per-query spans.

    Pass ``async_engine.sync_engine`` for an ``AsyncEngine``.
    """
    SQLAlchemyInstrumentor().instrument(engine=engine)
