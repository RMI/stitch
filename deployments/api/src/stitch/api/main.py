from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy.exc import OperationalError
from starlette.status import HTTP_503_SERVICE_UNAVAILABLE
from .middleware import register_middlewares
from .db.config import dispose_engine
from .auth import validate_auth_config_at_startup
from .observability import configure_logging, configure_tracing, instrument_fastapi
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
    if _tracer_provider is not None:
        # Flush any buffered spans (BatchSpanProcessor) before exit.
        _tracer_provider.shutdown()


def create_app(
    settings: Settings, *, tracer_provider: TracerProvider | None
) -> FastAPI:
    """Assemble the FastAPI application: middlewares, instrumentation, routers.

    ``tracer_provider`` is the value from :func:`configure_tracing` (``None`` when
    tracing is disabled); when set, the app is auto-instrumented. Note that
    ``FastAPIInstrumentor.instrument_app`` wraps its ASGI middleware *around the
    whole user middleware stack* (CORS included), so the order of the calls below
    does not affect the OpenTelemetry-vs-CORS layering.

    Extracted as a factory so tests can build an instrumented app; the shared
    module-level ``app`` runs uninstrumented under the test env.
    """
    application = FastAPI(lifespan=lifespan)
    register_middlewares(application=application, settings=settings)
    if tracer_provider is not None:
        instrument_fastapi(application)
    application.include_router(base_router)
    return application


settings = get_settings()

configure_logging(level=settings.log_level, log_format=settings.log_format)
_tracer_provider = configure_tracing(settings)

app = create_app(settings, tracer_provider=_tracer_provider)


# Global exception handler
# - this will catch all exceptions of this type, incl. things like db constraint violations
# - we can refine and narrow the scope at a a later point
@app.exception_handler(OperationalError)
async def db_unavailable_handler(_request: Request, _exc: OperationalError):
    return JSONResponse(
        status_code=HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Database unavailable."},
    )
