import logging
from typing import Final
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from stitch.api.admission import BatchYieldMiddleware
from stitch.api.observability import RequestTimingMiddleware
from stitch.api.settings import Settings

logger = logging.getLogger(__name__)

ALLOWED_METHODS: Final[tuple[str, ...]] = (
    "GET",
    "POST",
    "PUT",
    "DELETE",
    "OPTIONS",
)

ALLOWED_HEADERS: Final[tuple[str, ...]] = (
    "Authorization",
    "Content-Type",
    "Accept",
    "Origin",
)


def register_middlewares(application: FastAPI, settings: Settings):
    if settings.batch_yield_enabled:
        if settings.is_prod:
            # Warn rather than fail: unlike AUTH_DISABLED (a security hole, so
            # validate_auth_config_at_startup refuses outright), this is a perf
            # knob and should not crash prod because a var lingered in a shared
            # config. Not silently ignored, though — hence the warning.
            logger.warning(
                "BATCH_YIELD_ENABLED is set but ignored: the batch-yield gate is "
                "a dev/shared-server feature and is never active in prod."
            )
        else:
            # Added first, so it is the *innermost* user middleware: still
            # outside routing (a deferred request therefore resolves no
            # dependencies — no token verify, no DB session), but inside
            # RequestTimingMiddleware so the wait is included in the logged
            # duration_ms and can be correlated by request_id. Hiding the wait
            # would make the gate invisible in the very tooling used to verify
            # it; the gate's own log line carries gate_wait_ms to separate the
            # two.
            application.add_middleware(
                BatchYieldMiddleware,
                quiet_s=settings.batch_yield_quiet_ms / 1000.0,
                max_wait_s=settings.batch_yield_max_wait_ms / 1000.0,
            )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(settings.frontend_origin_url).rstrip("/")],
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
    )
    # Added last so it is the outermost middleware and times the full request,
    # including time spent in CORS handling.
    application.add_middleware(RequestTimingMiddleware)
