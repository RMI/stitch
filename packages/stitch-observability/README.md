# stitch-observability

Shared OpenTelemetry tracing setup + instrumentation for Stitch services, so
every service traces the same way and **interactions between services land in
one trace**.

```python
from stitch.observability import (
    configure_tracing, instrument_fastapi, instrument_httpx, shutdown_tracing,
    OTelSettings,
)

provider = configure_tracing(
    service_name="stitch-entity-linkage",
    enabled=settings.otel_enabled,
    exporter=settings.otel_traces_exporter,
    otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    sample_ratio=settings.otel_sample_ratio,
)
if provider is not None:
    instrument_fastapi(app)   # on the constructed app, before it serves
    instrument_httpx()        # outbound calls inject W3C traceparent
# ... shutdown_tracing(provider) on exit
```

- **`OTelSettings`** — pydantic-settings mixin with the shared `OTEL_*` fields;
  a service's `Settings` inherits it.
- **`instrument_httpx()`** — the propagation piece: outbound `httpx` calls carry
  `traceparent`, so a downstream service (FastAPI-instrumented) continues the
  same trace rather than starting a disconnected one.
- **`instrument_sqlalchemy(engine)`** — per-query spans for a (sync) engine; pass
  `async_engine.sync_engine` for an `AsyncEngine`.
- Exporter modes: `console` (spans → structured stdout logs, no sidecar),
  `otlp` (→ collector/Jaeger), `none` (disabled).

Each Stitch service calls `configure_tracing` at startup (before the app is
built), then `instrument_fastapi(app)` + the relevant `instrument_*` after the
app is constructed, and `shutdown_tracing(provider)` on exit. The API also wraps
this behind a thin `stitch.api.observability.tracing` shim that preserves its
historical surface.
