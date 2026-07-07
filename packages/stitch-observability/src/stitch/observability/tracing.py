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
    from collections.abc import Mapping, Sequence

    from fastapi import FastAPI
    from opentelemetry.sdk.trace import ReadableSpan
    from sqlalchemy.engine import Engine

    from .settings import OTelSettings

_span_logger = logging.getLogger("stitch.observability.trace")

# Bound attribute values before they are logged. Long strings — notably
# SQLAlchemy's ``db.statement`` (big IN (...) lists, wide CTEs) — and large array
# attributes would otherwise dump untruncated to stdout / Log Analytics. The
# per-string cap mirrors query_timing._normalize_statement's 2000-char limit.
_MAX_ATTR_CHARS = 2000
_MAX_ATTR_ITEMS = 100


def _truncate_str(value: str) -> str:
    if len(value) > _MAX_ATTR_CHARS:
        return value[:_MAX_ATTR_CHARS] + "…"
    return value


def _truncate_value(value: object) -> object:
    """Bound a single attribute value: cap long strings, and cap both the length
    and the per-element size of sequence (array) attributes. Scalars (bool / int
    / float) pass through unchanged."""
    if isinstance(value, str):
        return _truncate_str(value)
    if isinstance(value, (list, tuple)):
        capped: list = [
            _truncate_str(item) if isinstance(item, str) else item
            for item in value[:_MAX_ATTR_ITEMS]
        ]
        if len(value) > _MAX_ATTR_ITEMS:
            capped.append(f"…(+{len(value) - _MAX_ATTR_ITEMS} more)")
        return capped
    return value


def _truncate_attributes(attributes: dict) -> dict:
    """Bound over-long attribute values (strings and array attributes) so a span
    log record stays bounded."""
    return {key: _truncate_value(value) for key, value in attributes.items()}


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
                        "attributes": _truncate_attributes(dict(span.attributes or {})),
                        # Resource attributes (service.name, deployment.name, ...)
                        # so the stdout span stream carries the same deployment
                        # tags as the OTLP path, groupable across deployments/PRs.
                        "resource": dict(span.resource.attributes)
                        if span.resource is not None
                        else {},
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
    version: str | None = None,
    environment: str | None = None,
    extra_resource_attributes: "Mapping[str, str] | None" = None,
) -> TracerProvider | None:
    """Install the global tracer provider, or return ``None`` if disabled.

    Call once at startup, before the first span is created. Idempotency is not
    guaranteed — ``set_tracer_provider`` warns if called twice.
    """
    if not enabled or exporter == "none":
        return None

    # Only include keys we actually have a value for. Anything omitted is
    # supplied by the OTEL_RESOURCE_ATTRIBUTES / OTEL_SERVICE_NAME env vars,
    # which Resource.create() merges automatically — that is how deployment
    # metadata (deployment.name, deployment.lane, ...) gets stamped on every
    # span without per-service code. Passing an explicit value here would
    # override the env, so we must NOT pass placeholder "unknown"s.
    attributes: dict[str, str] = {"service.name": service_name}
    if version:
        attributes["service.version"] = version
    if environment:
        attributes["deployment.environment"] = environment
    if extra_resource_attributes:
        attributes.update(extra_resource_attributes)
    resource = Resource.create(attributes)
    sampler = ParentBased(root=TraceIdRatioBased(sample_ratio))
    provider = TracerProvider(resource=resource, sampler=sampler)

    if exporter == "otlp":
        # endpoint=None lets the exporter fall back to OTEL_EXPORTER_OTLP_ENDPOINT
        # / the localhost default.
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
        )
    else:  # "console" — log spans to stdout, no sidecar required.
        # SimpleSpanProcessor exports each span synchronously on the request
        # thread. Kept for immediate dev visibility (the otlp/cloud path already
        # batches); switch to BatchSpanProcessor if this hot-path cost matters.
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

    URL query strings are intentionally left intact on server spans — they are
    the diagnostic payload for the performance work this serves. When a retained
    cloud backend makes aggregate PII a concern, scrub them at the collector's
    egress (an ``attributes``/``redaction`` processor) rather than blinding local
    dev.
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


def setup_fastapi_tracing(
    app: "FastAPI",
    *,
    service_name: str,
    settings: "OTelSettings",
    instrument_outbound_httpx: bool = True,
    version: str | None = None,
    environment: str | None = None,
    extra_resource_attributes: "Mapping[str, str] | None" = None,
) -> "TracerProvider | None":
    """Configure tracing and instrument a FastAPI app, in one ordered step.

    Collapses the per-service wiring — :func:`configure_tracing` (reading the
    shared ``OTEL_*`` settings) then :func:`instrument_fastapi` (+ optional
    :func:`instrument_httpx`) — so the ordering lives in one place instead of
    being replicated (and drifting) across services. Call it *after* the app and
    its middleware are constructed but before it serves requests.

    Returns the provider (``None`` when tracing is disabled); the caller keeps it
    and calls :func:`shutdown_tracing` on shutdown. ``instrument_outbound_httpx``
    propagates the W3C ``traceparent`` on outbound httpx calls so downstream
    services continue the same trace — leave it on for any service that makes
    downstream HTTP calls.
    """
    provider = configure_tracing(
        service_name=service_name,
        enabled=settings.otel_enabled,
        exporter=settings.otel_traces_exporter,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        sample_ratio=settings.otel_sample_ratio,
        version=version,
        environment=environment,
        extra_resource_attributes=extra_resource_attributes,
    )
    if provider is not None:
        instrument_fastapi(app)
        if instrument_outbound_httpx:
            instrument_httpx()
    return provider


def setup_sqlalchemy_tracing(engine: "Engine", *, settings: "OTelSettings") -> bool:
    """Instrument a SQLAlchemy engine for per-query spans, if tracing is enabled.

    The engine-seam companion to :func:`setup_fastapi_tracing`. Unlike that
    helper it does **not** call :func:`configure_tracing` — the global provider is
    installed once at app startup, whereas engines are created lazily (often
    after startup, e.g. a cached ``get_engine``) and only need instrumenting.
    Guarded on the shared ``OTEL_*`` settings so a tracing-disabled service does
    not pay the per-query span-wrapping cost. Pass ``async_engine.sync_engine``
    for an ``AsyncEngine``. Returns whether the engine was instrumented.
    """
    if not settings.otel_enabled or settings.otel_traces_exporter == "none":
        return False
    instrument_sqlalchemy(engine)
    return True
