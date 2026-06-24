"""Integration-level checks that the downstream auth modes actually attach the
expected Authorization header on outgoing requests via AsyncStitchClient."""

from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager

import httpx
import pytest
from stitch.client import AsyncStitchClient
from stitch.client.auth import STITCH_CLIENT_BEARER_TOKEN_ENV_VAR

from stitch.service.auth import AuthMode, build_headers_provider


@asynccontextmanager
async def _capturing_client(
    seen: dict, headers_provider: Callable[[], Mapping[str, str]]
) -> AsyncIterator[AsyncStitchClient]:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, json={})

    # AsyncStitchClient does not own (or close) an injected client, so close the
    # raw transport ourselves to avoid leaking it.
    raw = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://downstream.test/api/v1",
    )
    try:
        yield AsyncStitchClient(client=raw, headers_provider=headers_provider)
    finally:
        await raw.aclose()


@pytest.mark.anyio
async def test_passthrough_mode_forwards_caller_token() -> None:
    seen: dict = {}
    provider = build_headers_provider(AuthMode.passthrough, token="caller-jwt")

    async with _capturing_client(seen, provider) as client:
        await client.get_auth_me()

    assert seen["authorization"] == "Bearer caller-jwt"


@pytest.mark.anyio
async def test_machine_mode_sends_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STITCH_CLIENT_BEARER_TOKEN_ENV_VAR, "machine-tok")
    seen: dict = {}
    provider = build_headers_provider(AuthMode.machine)

    async with _capturing_client(seen, provider) as client:
        await client.get_auth_me()

    assert seen["authorization"] == "Bearer machine-tok"
