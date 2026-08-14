from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from stitch.client import (
    AsyncStitchClient,
    STITCH_CLIENT_BEARER_TOKEN_ENV_VAR,
    StitchAPIError,
    env_bearer_token_headers_provider,
)
from stitch.entity_linkage.client import (
    StitchApiClient,
    validate_downstream_auth_config_at_startup,
)
from stitch.entity_linkage.settings import get_settings


def make_client(
    handler,
    *,
    base_url: str = "http://example.test/api/v1",
) -> StitchApiClient:
    shared_client = AsyncStitchClient(
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url=base_url,
        ),
        headers_provider=env_bearer_token_headers_provider(),
    )
    return StitchApiClient(client=shared_client)


def test_stitch_api_client_requires_env_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(STITCH_CLIENT_BEARER_TOKEN_ENV_VAR, raising=False)

    with pytest.raises(ValueError) as exc_info:
        validate_downstream_auth_config_at_startup()

    assert str(exc_info.value) == f"{STITCH_CLIENT_BEARER_TOKEN_ENV_VAR} must be set"


@pytest.mark.anyio
async def test_get_oil_gas_field_detail_maps_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(STITCH_CLIENT_BEARER_TOKEN_ENV_VAR, "token-123")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/oil-gas-fields/42/detail"
        assert request.headers["Authorization"] == "Bearer token-123"
        return httpx.Response(
            200,
            json={"id": 42, "data": {"name": "Alpha", "country": "US"}},
        )

    client = make_client(handler)

    detail = await client.get_oil_gas_field_detail(42)

    assert detail.id == 42
    assert detail.name == "Alpha"
    assert detail.country == "US"

    await client.aclose()


@pytest.mark.anyio
async def test_post_merge_sends_current_branch_payload_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(STITCH_CLIENT_BEARER_TOKEN_ENV_VAR, "token-123")
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"merged": True})

    client = make_client(handler)

    payload = await client.create_merge_candidate(resource_ids=[7, 8])

    assert payload == {"merged": True}
    assert captured == {
        "method": "POST",
        "path": "/api/v1/oil-gas-fields/merge-candidates",
        "authorization": "Bearer token-123",
        "body": {"resource_ids": [7, 8]},
    }

    await client.aclose()


@pytest.mark.parametrize(
    ("status_code", "text", "operation"),
    [
        (500, "server exploded", "GET /oil-gas-fields/"),
        (404, "missing", "GET /oil-gas-fields/123/detail"),
        (400, "bad request", "POST /oil-gas-fields/merge"),
    ],
)
def test_raise_for_status_raises_stitch_api_error(
    status_code: int,
    text: str,
    operation: str,
) -> None:
    response = httpx.Response(status_code, text=text)

    with pytest.raises(StitchAPIError) as exc_info:
        AsyncStitchClient._raise_for_status(response, operation)

    assert (
        str(exc_info.value) == f"{operation} failed with status {status_code}: {text}"
    )


def test_default_client_is_built_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeout and retry budget come from settings, not hardcoded values."""
    monkeypatch.setenv(STITCH_CLIENT_BEARER_TOKEN_ENV_VAR, "token-123")
    monkeypatch.setenv("ENTITY_LINKAGE_API_BASE_URL", "http://api.test/api/v1")
    monkeypatch.setenv("ENTITY_LINKAGE_API_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("ENTITY_LINKAGE_API_MAX_RETRIES", "4")
    get_settings.cache_clear()

    try:
        client = StitchApiClient()
    finally:
        # get_settings is lru_cached, so leaving this populated would leak the
        # patched environment into every later test in the session.
        get_settings.cache_clear()

    shared = client._client
    assert str(shared._client.base_url).rstrip("/") == "http://api.test/api/v1"
    assert shared._client.timeout.read == 45.0
    assert shared._max_retries == 4
