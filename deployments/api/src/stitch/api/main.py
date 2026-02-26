from contextlib import asynccontextmanager
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.status import HTTP_503_SERVICE_UNAVAILABLE
from .middleware import register_middlewares
from .db.config import dispose_engine
from .auth import validate_auth_config_at_startup
from .settings import get_settings

from .routers.resources import router as resource_router
from .routers.health import router as health_router
from stitch.api.routers.oilgasfields import router as oilgas_fields_router

base_router = APIRouter(prefix="/api/v1")
base_router.include_router(resource_router)
base_router.include_router(health_router)
base_router.include_router(oilgas_fields_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_auth_config_at_startup()
    yield
    await dispose_engine()


app = FastAPI(lifespan=lifespan)

settings = get_settings()

register_middlewares(application=app, settings=settings)

app.include_router(base_router)


# Global exception handler
# - this will catch all exceptions of this type, incl. things like db constraint violations
# - we can refine and narrow the scope at a a later point
@app.exception_handler(OperationalError)
async def db_unavailable_handler(_request: Request, _exc: OperationalError):
    return JSONResponse(
        status_code=HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Database unavailable."},
    )
