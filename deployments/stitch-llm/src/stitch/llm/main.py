from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI
from stitch.observability import (
    configure_logging,
    configure_tracing,
    instrument_fastapi,
    instrument_httpx,
    resource_attributes_from_env,
    shutdown_tracing,
)

from stitch.llm.auth import validate_auth_config_at_startup
from stitch.llm.client import validate_downstream_auth_config_at_startup
from stitch.llm.middleware import register_middlewares
from stitch.llm.routers.health import router as health_router
from stitch.llm.routers.oil_gas_fields import router as oil_gas_fields_router
from stitch.llm.settings import get_settings

base_router = APIRouter(prefix="/api/v1")
base_router.include_router(health_router)
base_router.include_router(oil_gas_fields_router)

# Assigned below once settings are loaded; declared here so `lifespan` (which
# reads it) can't NameError if an import between here and the assignment fails.
_tracer_provider = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.started_at = datetime.now(UTC)
    app.state.auth_config_validated = False
    app.state.downstream_auth_config_validated = False
    validate_auth_config_at_startup()
    app.state.auth_config_validated = True
    validate_downstream_auth_config_at_startup()
    app.state.downstream_auth_config_validated = True
    yield
    shutdown_tracing(_tracer_provider)


settings = get_settings()

# Structured JSON logs on the root logger, stamped with the same deployment
# metadata (deployment.name / lane / service.version) that the tracing SDK puts
# on spans, so logs and traces are comparable across deployments/PRs.
configure_logging(
    level=settings.log_level,
    resource_attributes=resource_attributes_from_env(),
)

_tracer_provider = configure_tracing(
    service_name="stitch-llm",
    enabled=settings.otel_enabled,
    exporter=settings.otel_traces_exporter,
    otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    sample_ratio=settings.otel_sample_ratio,
)

app = FastAPI(lifespan=lifespan)

register_middlewares(application=app, settings=settings)

if _tracer_provider is not None:
    instrument_fastapi(app)
    # Propagates the W3C traceparent on outbound httpx calls (Azure OpenAI +
    # the downstream stitch-client), linking them into the same trace.
    instrument_httpx()

app.include_router(base_router)
