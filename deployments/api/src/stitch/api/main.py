from contextlib import asynccontextmanager
from fastapi import APIRouter, FastAPI
from stitch.api.db.config import dispose_engine

from .routers.resources import router as resource_router
from .routers.health import router as health_router

base_router = APIRouter(prefix="/api/v1")
base_router.include_router(resource_router)
base_router.include_router(health_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await dispose_engine()


app = FastAPI(lifespan=lifespan)


@base_router.get("/")
async def root():
    return {"message": "Hello from Stitch API!"}


app.include_router(base_router)
