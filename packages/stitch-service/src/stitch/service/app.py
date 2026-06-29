from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI
from stitch.observability import (
    OTelSettings,
    configure_tracing,
    instrument_fastapi,
    instrument_httpx,
    shutdown_tracing,
)

from .middleware import register_cors

#: A startup/shutdown hook: receives the app, may be sync or async.
LifecycleHook = Callable[[FastAPI], Awaitable[None] | None]


async def _maybe_await(value: Awaitable[None] | None) -> None:
    if inspect.isawaitable(value):
        return await value
    return None


def create_app(
    *,
    title: str | None = None,
    routers: Sequence[APIRouter] = (),
    api_prefix: str = "/api/v1",
    cors_origins: Sequence[str] = (),
    on_startup: LifecycleHook | None = None,
    on_shutdown: LifecycleHook | None = None,
    service_name: str | None = None,
    otel: OTelSettings | None = None,
    version: str = "unknown",
    environment: str = "unknown",
    **fastapi_kwargs: object,
) -> FastAPI:
    """Build a FastAPI app with the scaffolding every non-core service repeats.

    Sets ``app.state.started_at`` for health/uptime, registers CORS, mounts the
    given routers under ``api_prefix``, and runs the optional ``on_startup`` /
    ``on_shutdown`` hooks inside the lifespan.

    Pass ``service_name`` + ``otel`` to enable OpenTelemetry: the global tracer
    provider is configured before the app is built, the app and outbound httpx
    are instrumented synchronously (before serving — not in ``on_startup``,
    where middleware-stack timing makes FastAPI instrumentation ineffective),
    and the provider is flushed/shut down on exit. Omit them to leave tracing
    off (current behavior).
    """
    # Configure the global provider before the app exists; instrument the built
    # app below (before it serves). `provider is None` when tracing is disabled.
    provider = None
    if service_name is not None and otel is not None:
        provider = configure_tracing(
            service_name=service_name,
            enabled=otel.otel_enabled,
            exporter=otel.otel_traces_exporter,
            otlp_endpoint=otel.otel_exporter_otlp_endpoint,
            otlp_protocol=otel.otel_exporter_otlp_protocol,
            sample_ratio=otel.otel_sample_ratio,
            version=version,
            environment=environment,
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.started_at = datetime.now(UTC)
        if on_startup is not None:
            await _maybe_await(on_startup(app))
        yield
        if on_shutdown is not None:
            await _maybe_await(on_shutdown(app))
        shutdown_tracing(provider)

    if title is not None:
        fastapi_kwargs["title"] = title
    app = FastAPI(lifespan=lifespan, **fastapi_kwargs)

    register_cors(app, origins=cors_origins)

    if provider is not None:
        instrument_fastapi(app)
        instrument_httpx()

    base_router = APIRouter(prefix=api_prefix)
    for router in routers:
        base_router.include_router(router)
    app.include_router(base_router)

    return app
