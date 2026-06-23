"""Shared FastAPI scaffolding for Stitch non-core services.

Provides the app factory, CORS wiring, health helpers, and the auth seam (both
inbound request validation and the downstream machine / on-behalf-of modes) that
every service otherwise copies. Observability is intentionally out of scope for
now (in flight on a separate branch); the app factory leaves lifecycle hooks
open so it can be added later.
"""

from .app import create_app
from .auth import (
    AuthMode,
    RequestAuthContext,
    ServiceAuth,
    ServiceUser,
    build_headers_provider,
    machine_token_headers_provider,
    relay_token_headers_provider,
)
from .health import (
    format_started_at,
    make_basic_health_router,
    runtime_block,
    uptime_seconds,
)
from .middleware import register_cors

__all__ = [
    "AuthMode",
    "RequestAuthContext",
    "ServiceAuth",
    "ServiceUser",
    "build_headers_provider",
    "create_app",
    "format_started_at",
    "machine_token_headers_provider",
    "make_basic_health_router",
    "register_cors",
    "relay_token_headers_provider",
    "runtime_block",
    "uptime_seconds",
]
