from fastapi import FastAPI
from stitch.service import create_app

from stitch.llm.auth import validate_auth_config_at_startup
from stitch.llm.client import validate_downstream_auth_config_at_startup
from stitch.llm.routers.health import router as health_router
from stitch.llm.routers.oil_gas_fields import router as oil_gas_fields_router
from stitch.llm.settings import get_settings


def _run_startup(app: FastAPI) -> None:
    app.state.auth_config_validated = False
    app.state.downstream_auth_config_validated = False
    validate_auth_config_at_startup()
    app.state.auth_config_validated = True
    validate_downstream_auth_config_at_startup()
    app.state.downstream_auth_config_validated = True


settings = get_settings()

app = create_app(
    routers=[health_router, oil_gas_fields_router],
    cors_origins=[str(settings.frontend_origin_url)],
    on_startup=_run_startup,
    service_name="stitch-llm",
    otel=settings,
)
