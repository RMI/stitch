from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy.exc import OperationalError
from starlette.status import HTTP_503_SERVICE_UNAVAILABLE
from stitch.observability import (
    configure_logging,
    configure_tracing,
    instrument_fastapi,
    instrument_httpx,
    resource_attributes_from_env,
    shutdown_tracing,
)
from .middleware import register_middlewares
from .db.config import dispose_engine
from .auth import validate_auth_config_at_startup
from .settings import Settings, get_settings

from .routers.auth import router as auth_router
from .routers.health import router as health_router
from .routers.oil_gas_fields import router as ogfield_resource_router
from .routers.oil_gas_field_sources import router as ogfield_source_router

base_router = APIRouter(prefix="/api/v1")
base_router.include_router(auth_router)
base_router.include_router(health_router)
base_router.include_router(ogfield_resource_router)
base_router.include_router(ogfield_source_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.started_at = datetime.now(UTC)
    app.state.auth_config_validated = False
    validate_auth_config_at_startup()
    app.state.auth_config_validated = True
    yield
    await dispose_engine()
    # Flush any buffered spans (BatchSpanProcessor) before exit, using the
    # provider this app was built with (attached in create_app), so a
    # factory-built app shuts down its own provider rather than a module global.
    # No-op if tracing is disabled (provider is None).
    shutdown_tracing(getattr(app.state, "tracer_provider", None))


# Global exception handler
# - this will catch all exceptions of this type, incl. things like db constraint
#   violations
# - we can refine and narrow the scope at a later point
async def db_unavailable_handler(_request: Request, _exc: OperationalError):
    return JSONResponse(
        status_code=HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Database unavailable."},
    )


def create_app(
    settings: Settings, *, tracer_provider: TracerProvider | None
) -> FastAPI:
    """Assemble the FastAPI application: middlewares, instrumentation, routers,
    exception handlers.

    Single source of truth for app assembly — both the module-level singleton
    and the instrumentation tests build through here, so the two can't drift.

    ``tracer_provider`` mirrors the return of the shared tracing setup (``None``
    when tracing is disabled); when set, the app is auto-instrumented via
    :func:`instrument_fastapi`. It is also stored on ``app.state.tracer_provider``
    so ``lifespan`` flushes the provider this app was built with rather than a
    module global. Note that ``FastAPIInstrumentor.instrument_app`` wraps its ASGI
    middleware *around the whole user middleware stack* (CORS included), so the
    order of the calls below does not affect the OpenTelemetry-vs-CORS layering.
    """
    application = FastAPI(lifespan=lifespan)
    application.state.tracer_provider = tracer_provider
    register_middlewares(application=application, settings=settings)
    if tracer_provider is not None:
        instrument_fastapi(application)
    application.include_router(base_router)
    application.add_exception_handler(OperationalError, db_unavailable_handler)
    return application


settings = get_settings()

configure_logging(
    level=settings.log_level,
    log_format=settings.log_format,
    # Stamp the same deployment metadata (deployment.name / lane / service.version)
    # onto every log record that the tracing SDK stamps on spans, so logs and
    # traces are comparable across deployments/PRs. Sourced from the shared
    # OTEL_RESOURCE_ATTRIBUTES / OTEL_SERVICE_NAME env.
    resource_attributes=resource_attributes_from_env(),
)

# Unlike entity-linkage / stitch-llm (which call the shared ``setup_fastapi_tracing``
# one-shot), the API splits tracing *configuration* from app *assembly*: configure
# the global provider here, then let ``create_app`` own ``instrument_fastapi``. That
# keeps a single app-assembly path — shared with the instrumentation tests, which
# pass their own provider — and avoids double-instrumenting. SQLAlchemy per-query
# spans are set up separately in db/config.py, since the engine is created lazily.
_tracer_provider = configure_tracing(
    service_name="stitch-api",
    enabled=settings.otel_enabled,
    exporter=settings.otel_traces_exporter,
    otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    sample_ratio=settings.otel_sample_ratio,
    # None (not "unknown") when unset, so an env-provided service.version via
    # OTEL_RESOURCE_ATTRIBUTES isn't clobbered by a placeholder.
    version=settings.app_version,
    environment=settings.environment_name,
)
app = create_app(settings, tracer_provider=_tracer_provider)

# Instrument outbound httpx as a process-global step (kept out of ``create_app``
# so the instrumentation tests, which build through it with a real provider,
# don't patch httpx for their test client). The API makes few/no outbound httpx
# calls today, so this is close to a no-op — but when it does make one (e.g. a
# JWKS fetch, or a future downstream call), it's captured as a client span and
# carries ``traceparent`` for free, rather than being a silent gap in the trace.
if _tracer_provider is not None:
    instrument_httpx()
