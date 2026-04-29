from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

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
    validate_auth_config_at_startup()
    yield


app = FastAPI(lifespan=lifespan)

settings = get_settings()

register_middlewares(application=app, settings=settings)

app.include_router(base_router)
