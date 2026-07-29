from contextlib import asynccontextmanager
from datetime import UTC, datetime
from fastapi import APIRouter, FastAPI
from stitch.observability import (
    configure_logging,
    resource_attributes_from_env,
    setup_fastapi_tracing,
    shutdown_tracing,
)
from .middleware import register_middlewares
from .auth import validate_auth_config_at_startup
from .client import validate_downstream_auth_config_at_startup
from .settings import get_settings

from .routers.health import router as health_router
from .routers.link import router as link_router
from .routers.start import router as start_router

base_router = APIRouter(prefix="/api/v1")
base_router.include_router(health_router)
base_router.include_router(start_router)
base_router.include_router(link_router)

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

app = FastAPI(lifespan=lifespan)

register_middlewares(application=app, settings=settings)

# Configure tracing, then instrument server spans + outbound httpx (traceparent
# propagation to the API), in the package's defined order.
_tracer_provider = setup_fastapi_tracing(
    app,
    service_name="stitch-entity-linkage",
    settings=settings,
)

app.include_router(base_router)
