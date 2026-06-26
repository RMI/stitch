# stitch-service

Shared FastAPI scaffolding for Stitch non-core services — the boilerplate that
`entity-linkage`, the ETL services, and `stitch-llm` otherwise each copy.

- `create_app(...)` — app factory: sets `app.state.started_at`, registers CORS,
  mounts routers under `/api/v1`, and runs service-provided startup/shutdown
  hooks inside the lifespan.
- `register_cors(app, origins=...)` — the standard CORS policy.
- health helpers — `make_basic_health_router(service)` for liveness, plus
  `runtime_block`/`format_started_at`/`uptime_seconds` for assembling a
  service-specific `/health/details`.

```python
from stitch.service import create_app

def _startup(app):
    validate_auth_config_at_startup()
    validate_downstream_auth_config_at_startup()

app = create_app(
    routers=[health_router, start_router],
    cors_origins=[str(settings.frontend_origin_url)],
    on_startup=_startup,
)
```

## Out of scope (for now)

- **Observability/logging** — in flight on a separate branch; will hook into the
  app factory's lifespan later.
- **Auth** — each service still owns its auth wiring (settings-coupled); a future
  pass may extract a configurable auth provider here.
