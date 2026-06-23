from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI

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
    **fastapi_kwargs: object,
) -> FastAPI:
    """Build a FastAPI app with the scaffolding every non-core service repeats.

    Sets ``app.state.started_at`` for health/uptime, registers CORS, mounts the
    given routers under ``api_prefix``, and runs the optional ``on_startup`` /
    ``on_shutdown`` hooks inside the lifespan.

    ``on_startup`` is where a service does its own startup validation (auth /
    downstream config). Keeping it a service-provided callback — rather than
    baking specific validators in here — lets each service own and test that
    logic. Observability wiring (deferred to a later pass) will hook in here
    too, without reshaping this signature.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.started_at = datetime.now(UTC)
        if on_startup is not None:
            await _maybe_await(on_startup(app))
        yield
        if on_shutdown is not None:
            await _maybe_await(on_shutdown(app))

    if title is not None:
        fastapi_kwargs["title"] = title
    app = FastAPI(lifespan=lifespan, **fastapi_kwargs)

    register_cors(app, origins=cors_origins)

    base_router = APIRouter(prefix=api_prefix)
    for router in routers:
        base_router.include_router(router)
    app.include_router(base_router)

    return app
