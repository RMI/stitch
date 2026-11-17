from fastapi import FastAPI, APIRouter
from .routers import og_field_router, og_field_source_router, og_field_merge_router

app = FastAPI()
_base_router = APIRouter(
    prefix="/oil-gas-fields",
    responses={404: {"description": "Not found"}},
)
_base_router.include_router(og_field_router)
_base_router.include_router(og_field_source_router, prefix="/sources")
_base_router.include_router(og_field_merge_router, prefix="/merges")

app.include_router(_base_router)

__all__ = ["app"]
