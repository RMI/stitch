from contextlib import asynccontextmanager
from datetime import UTC, datetime
from fastapi import APIRouter, FastAPI
from .middleware import register_middlewares
from .auth import validate_auth_config_at_startup
from .client import validate_downstream_auth_config_at_startup
from .settings import get_settings

from .routers.health import router as health_router
from .routers.start import router as start_router

base_router = APIRouter(prefix="/api/v1")
base_router.include_router(health_router)
base_router.include_router(start_router)


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


app = FastAPI(lifespan=lifespan)

settings = get_settings()

register_middlewares(application=app, settings=settings)

app.include_router(base_router)
