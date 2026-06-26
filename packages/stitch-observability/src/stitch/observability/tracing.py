"""Shared OpenTelemetry tracing setup for Stitch services.

Span *generation* is handled by auto-instrumentation (FastAPI, httpx,
SQLAlchemy); this module owns span *export*, configurable via the exporter mode:

* ``console`` (default) — finished spans are emitted as structured log records
  (see :class:`LoggingSpanExporter`), so local dev gets full trace data on
  stdout **without** running the collector / Jaeger sidecars.
* ``otlp`` — spans are shipped via OTLP/gRPC to the collector (``→`` Jaeger).
* ``none`` — tracing is disabled entirely.

Sampling uses ``ParentBased(root=TraceIdRatioBased(ratio))`` so a service honors
an upstream caller's sampling decision (propagated via the W3C ``traceparent``
header) and only samples independently when it is the root of a trace.
"""

import logging
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
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

_span_logger = logging.getLogger("stitch.observability.trace")


def get_tracer(name: str) -> trace.Tracer:
    """Return a tracer from the global provider (no-op when tracing is off)."""
    return trace.get_tracer(name)


class LoggingSpanExporter(SpanExporter):
    """Export finished spans as structured log records instead of shipping them
    to a collector.

    Each span becomes one ``stitch.observability.trace`` log record whose
    ``event`` dict a JSON log formatter can flatten, so fields like ``trace_id``
    / ``duration_ms`` sit alongside request / query events on the same stream.
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


def configure_tracing(
    *,
    service_name: str,
    enabled: bool = True,
    exporter: str = "console",
    otlp_endpoint: str | None = None,
    sample_ratio: float = 1.0,
    version: str = "unknown",
    environment: str = "unknown",
) -> TracerProvider | None:
    """Install the global tracer provider, or return ``None`` if disabled.

    Call once at startup, before the first span is created. Idempotency is not
    guaranteed — ``set_tracer_provider`` warns if called twice.
    """
    if not enabled or exporter == "none":
        return None

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": version or "unknown",
            "deployment.environment": environment,
        }
    )
    sampler = ParentBased(root=TraceIdRatioBased(sample_ratio))
    provider = TracerProvider(resource=resource, sampler=sampler)

    if exporter == "otlp":
        # endpoint=None lets the exporter fall back to OTEL_EXPORTER_OTLP_ENDPOINT
        # / the localhost default.
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
        )
    else:  # "console" — log spans to stdout, no sidecar required.
        provider.add_span_processor(SimpleSpanProcessor(LoggingSpanExporter()))

    trace.set_tracer_provider(provider)
    return provider


def shutdown_tracing(provider: TracerProvider | None) -> None:
    """Flush and shut down the provider (e.g. a BatchSpanProcessor) on exit."""
    if provider is not None:
        provider.shutdown()


def instrument_fastapi(app: "FastAPI") -> None:
    """Auto-instrument a FastAPI app (server spans + traceparent extraction).

    Run on the constructed app before it serves requests — not inside a startup
    hook, where middleware-stack timing makes it ineffective. Imported lazily so
    the instrumentor's optional ``fastapi`` dependency is only required by
    services that actually call this.
    """
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)


def instrument_httpx() -> None:
    """Auto-instrument httpx so outbound calls inject the W3C ``traceparent``.

    This is what links a service's downstream calls (via ``AsyncStitchClient`` /
    the Azure client) into the same trace the receiving service continues.
    Imported lazily so the instrumentor's optional ``httpx`` dependency is only
    required by services that actually call this.
    """
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()


def instrument_sqlalchemy(engine: "Engine") -> None:
    """Auto-instrument a (sync) SQLAlchemy engine for per-query spans.

    Pass ``async_engine.sync_engine`` for an ``AsyncEngine``. Imported lazily so
    services without SQLAlchemy (the instrumentor lists it as an optional
    "instruments" dependency) don't need it installed to use this package.
    """
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(engine=engine)
