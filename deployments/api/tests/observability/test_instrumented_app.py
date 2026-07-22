"""Regression tests for the OpenTelemetry instrumentation + CORS interaction.

These build the app via :func:`create_app` with instrumentation *enabled*. The
shared test ``app`` cannot cover this: the rootdir ``conftest.py`` sets
``OTEL_TRACES_EXPORTER=none`` before import, so the singleton is never
instrumented and the OpenTelemetry ASGI middleware — the layer that regressed —
is absent from its stack.

The guarded-against failure: with FastAPI >=0.137 ``app.routes`` contains
``_IncludedRouter`` nodes that have no ``.path``. ``opentelemetry-instrumentation-fastapi``
(pre-fix) read ``.path`` on a *partial* route match (e.g. a CORS preflight, where
the path matches but the method does not), raising
``AttributeError: '_IncludedRouter' object has no attribute 'path'`` and 500-ing
the request inside instrumentation — before CORS could attach its headers, which
the browser surfaced as ``Failed to fetch``.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace import TracerProvider

from stitch.api.main import create_app
from stitch.api.settings import get_settings


@pytest.fixture
async def instrumented_client() -> AsyncIterator[AsyncClient]:
    """AsyncClient over an app built by ``create_app`` with OTel instrumentation on.

    A real ``TracerProvider`` is passed so ``create_app`` installs the
    OpenTelemetry ASGI middleware; the spans it produces go to the default
    provider and are irrelevant to what these tests assert.
    """
    app = create_app(get_settings(), tracer_provider=TracerProvider())
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test/api/v1",
    ) as ac:
        yield ac


@pytest.fixture
def allowed_origin() -> str:
    """The configured CORS origin (the Settings default under the test env)."""
    return str(get_settings().frontend_origin_url).rstrip("/")


@pytest.mark.anyio
async def test_instrumented_partial_match_does_not_crash(
    instrumented_client: AsyncClient,
):
    """A bare OPTIONS to a GET-only route must route normally, not 500.

    ``OPTIONS /api/v1/auth/me`` with no ``Access-Control-Request-Method`` header
    is not a CORS preflight, so ``CORSMiddleware`` does not short-circuit it and
    it reaches the OpenTelemetry middleware regardless of middleware order,
    producing a *partial* route match. Pre-fix this raised the
    ``_IncludedRouter`` ``AttributeError`` and returned 500; it must instead
    route to a 405 (method not allowed).
    """
    response = await instrumented_client.options("/auth/me")

    assert response.status_code == 405


@pytest.mark.anyio
async def test_instrumented_preflight_returns_cors_headers(
    instrumented_client: AsyncClient, allowed_origin: str
):
    """A real CORS preflight to /auth/me succeeds and carries CORS headers.

    End-to-end reproduction of the browser ``Failed to fetch``: the preflight
    must return a 2xx whose ``Access-Control-Allow-Origin`` header is present, so
    the browser releases the follow-up authenticated request.
    """
    response = await instrumented_client.options(
        "/auth/me",
        headers={
            "Origin": allowed_origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") == allowed_origin
