"""Integration-level checks that the downstream auth modes actually attach the
expected Authorization header on outgoing requests via AsyncStitchClient."""

from collections.abc import Callable, Mapping

import httpx
import pytest
from stitch.client import AsyncStitchClient
from stitch.client.auth import STITCH_CLIENT_BEARER_TOKEN_ENV_VAR

from stitch.service.auth import AuthMode, build_headers_provider


def _capturing_client(
    seen: dict, headers_provider: Callable[[], Mapping[str, str]]
) -> AsyncStitchClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, json={})

    raw = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://downstream.test/api/v1",
    )
    return AsyncStitchClient(client=raw, headers_provider=headers_provider)


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
