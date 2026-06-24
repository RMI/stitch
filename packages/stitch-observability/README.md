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
- Exporter modes: `console` (spans → structured stdout logs, no sidecar),
  `otlp` (→ collector/Jaeger), `none` (disabled).

`stitch-service`'s `create_app` wires this automatically when given a
`service_name` + `OTelSettings`; `stitch-jobs` emits a `job.run` span per run
via the global tracer (no-op when tracing is off).
