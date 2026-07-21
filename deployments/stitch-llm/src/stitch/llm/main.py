from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI
from stitch.client import validate_downstream_auth_at_startup

from stitch.llm.auth import validate_auth_config_at_startup
from stitch.llm.middleware import register_middlewares
from stitch.llm.routers.health import router as health_router
from stitch.llm.routers.oil_gas_fields import router as oil_gas_fields_router
from stitch.llm.settings import get_settings

base_router = APIRouter(prefix="/api/v1")
base_router.include_router(health_router)
base_router.include_router(oil_gas_fields_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.started_at = datetime.now(UTC)
    app.state.auth_config_validated = False
    app.state.downstream_auth_config_validated = False
    validate_auth_config_at_startup()
    app.state.auth_config_validated = True
    await validate_downstream_auth_at_startup(
        api_base_url=str(get_settings().api_base_url)
    )
    app.state.downstream_auth_config_validated = True
    yield


app = FastAPI(lifespan=lifespan)

settings = get_settings()

register_middlewares(application=app, settings=settings)

app.include_router(base_router)
