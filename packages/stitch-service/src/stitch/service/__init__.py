"""Shared FastAPI scaffolding for Stitch non-core services.

Provides the app factory, CORS wiring, and health helpers that every service
otherwise copies. Observability and auth extraction are intentionally out of
scope for now (observability is in flight on a separate branch); the app
factory leaves lifecycle hooks open so they can be added later.
"""

from .app import create_app
from .health import (
    format_started_at,
    make_basic_health_router,
    runtime_block,
    uptime_seconds,
)
from .middleware import register_cors

__all__ = [
    "create_app",
    "format_started_at",
    "make_basic_health_router",
    "register_cors",
    "runtime_block",
    "uptime_seconds",
]
