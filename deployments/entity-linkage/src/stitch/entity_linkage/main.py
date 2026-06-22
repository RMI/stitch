from fastapi import FastAPI
from stitch.service import create_app

from .auth import validate_auth_config_at_startup
from .client import validate_downstream_auth_config_at_startup
from .settings import get_settings

from .routers.health import router as health_router
from .routers.start import router as start_router


def _run_startup(app: FastAPI) -> None:
    app.state.auth_config_validated = False
    app.state.downstream_auth_config_validated = False
    validate_auth_config_at_startup()
    app.state.auth_config_validated = True
    validate_downstream_auth_config_at_startup()
    app.state.downstream_auth_config_validated = True


settings = get_settings()

app = create_app(
    routers=[health_router, start_router],
    cors_origins=[str(settings.frontend_origin_url)],
    on_startup=_run_startup,
)
