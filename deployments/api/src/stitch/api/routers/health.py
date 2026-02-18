from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.status import HTTP_200_OK


router = APIRouter()


# TODO: consider adding Claims/CurrentUser dependency.
# * do we want to allow unauthenticated users to hit `/health`?
@router.get("/health")
async def check_health():
    return JSONResponse({"status": "ok"}, status_code=HTTP_200_OK)
