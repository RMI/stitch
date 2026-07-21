from __future__ import annotations

import asyncio
import dataclasses
import json

import httpx
import pytest

from stitch.client import (
    Auth0M2MAuth,
    StitchAuthError,
    StitchClientConfig,
    validate_downstream_auth_at_startup,
)
from stitch.client.auth import fetch_auth_jwt

_ALL_VARS = {
    "STITCH_AUTH_CLIENT_ID": "cid",
    "STITCH_AUTH_CLIENT_SECRET": "csec",
    "STITCH_AUTH_AUDIENCE": "https://api.test",
    "STITCH_AUTH_ISSUER_URL": "https://issuer.test",
    "STITCH_API_BASE_URL": "https://api.test/v1",
}

_M2M_VARS = (
    "STITCH_AUTH_CLIENT_ID",
    "STITCH_AUTH_CLIENT_SECRET",
    "STITCH_AUTH_AUDIENCE",
    "STITCH_AUTH_ISSUER_URL",
)


def _set_all(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _ALL_VARS.items():
        monkeypatch.setenv(k, v)


def _clear_m2m_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (*_M2M_VARS, "STITCH_API_BASE_URL"):
        monkeypatch.delenv(var, raising=False)


def test_from_env_returns_config_when_all_vars_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_all(monkeypatch)

    config = StitchClientConfig.from_env()

    assert config.client_id == "cid"
    assert config.client_secret == "csec"
    assert config.audience == "https://api.test"
    assert config.auth_issuer_url == "https://issuer.test"
    assert config.api_base_url == "https://api.test/v1"


def test_from_env_raises_with_single_missing_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_all(monkeypatch)
    monkeypatch.delenv("STITCH_AUTH_AUDIENCE")

    with pytest.raises(StitchAuthError) as exc_info:
        StitchClientConfig.from_env()

    assert "STITCH_AUTH_AUDIENCE" in str(exc_info.value)


def test_from_env_lists_all_missing_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_all(monkeypatch)
    monkeypatch.delenv("STITCH_AUTH_CLIENT_ID")
    monkeypatch.delenv("STITCH_API_BASE_URL")

    with pytest.raises(StitchAuthError) as exc_info:
        StitchClientConfig.from_env()

    message = str(exc_info.value)
    assert "STITCH_AUTH_CLIENT_ID" in message
    assert "STITCH_API_BASE_URL" in message


def test_from_env_treats_empty_string_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_all(monkeypatch)
    monkeypatch.setenv("STITCH_AUTH_CLIENT_ID", "")

    with pytest.raises(StitchAuthError) as exc_info:
        StitchClientConfig.from_env()

    assert "STITCH_AUTH_CLIENT_ID" in str(exc_info.value)


def test_config_is_frozen() -> None:
    config = StitchClientConfig(
        client_id="cid",
        client_secret="csec",
        audience="https://api.test",
        auth_issuer_url="https://issuer.test",
        api_base_url="https://api.test/v1",
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        config.client_id = "other"


def _config() -> StitchClientConfig:
    return StitchClientConfig(
        client_id="cid",
        client_secret="csec",
        audience="https://api.test",
        auth_issuer_url="https://issuer.test",
        api_base_url="https://api.test/v1",
    )


@pytest.mark.anyio
async def test_fetch_auth_jwt_posts_client_credentials_payload() -> None:
    captured: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = json.loads(req.content)
        return httpx.Response(
            200,
            json={
                "access_token": "tok-123",
                "token_type": "Bearer",
                "expires_in": 86400,
            },
        )

    token = await fetch_auth_jwt(_config(), transport=httpx.MockTransport(handler))

    assert token == "tok-123"
    assert captured["url"] == "https://issuer.test/oauth/token"
    assert captured["body"] == {
        "client_id": "cid",
        "client_secret": "csec",
        "audience": "https://api.test",
        "grant_type": "client_credentials",
    }


@pytest.mark.anyio
async def test_fetch_auth_jwt_raises_on_non_200() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    with pytest.raises(StitchAuthError) as exc_info:
        await fetch_auth_jwt(_config(), transport=httpx.MockTransport(handler))

    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_fetch_auth_jwt_raises_on_missing_access_token() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    with pytest.raises(StitchAuthError) as exc_info:
        await fetch_auth_jwt(_config(), transport=httpx.MockTransport(handler))

    assert "access_token" in str(exc_info.value)


@pytest.mark.anyio
async def test_fetch_auth_jwt_raises_on_invalid_json() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    with pytest.raises(StitchAuthError) as exc_info:
        await fetch_auth_jwt(_config(), transport=httpx.MockTransport(handler))

    assert "JSON" in str(exc_info.value)


@pytest.mark.anyio
async def test_fetch_auth_jwt_wraps_transport_errors() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(StitchAuthError) as exc_info:
        await fetch_auth_jwt(_config(), transport=httpx.MockTransport(handler))

    assert "Auth0 token request failed" in str(exc_info.value)


def _counter_fetcher():
    state = {"n": 0}

    async def fetcher() -> str:
        state["n"] += 1
        return f"tok-{state['n']}"

    return state, fetcher


@pytest.mark.anyio
async def test_auth_first_request_fetches_token_and_attaches_bearer() -> None:
    seen_headers: list[str | None] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen_headers.append(req.headers.get("Authorization"))
        return httpx.Response(200, json={})

    state, fetcher = _counter_fetcher()
    auth = Auth0M2MAuth(fetcher)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.test",
        auth=auth,
    ) as client:
        await client.get("/x")

    assert seen_headers == ["Bearer tok-1"]
    assert state["n"] == 1


@pytest.mark.anyio
async def test_auth_reuses_token_across_subsequent_requests() -> None:
    seen_headers: list[str | None] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen_headers.append(req.headers.get("Authorization"))
        return httpx.Response(200, json={})

    state, fetcher = _counter_fetcher()
    auth = Auth0M2MAuth(fetcher)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.test",
        auth=auth,
    ) as client:
        await client.get("/x")
        await client.get("/y")

    assert seen_headers == ["Bearer tok-1", "Bearer tok-1"]
    assert state["n"] == 1


@pytest.mark.anyio
async def test_auth_refetches_once_on_401_then_succeeds() -> None:
    seen_headers: list[str | None] = []
    responses = iter([401, 200])

    def handler(req: httpx.Request) -> httpx.Response:
        seen_headers.append(req.headers.get("Authorization"))
        return httpx.Response(next(responses), json={})

    state, fetcher = _counter_fetcher()
    auth = Auth0M2MAuth(fetcher)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.test",
        auth=auth,
    ) as client:
        response = await client.get("/x")

    assert response.status_code == 200
    assert seen_headers == ["Bearer tok-1", "Bearer tok-2"]
    assert state["n"] == 2


@pytest.mark.anyio
async def test_auth_401_on_retry_surfaces_as_response() -> None:
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(401, json={})

    state, fetcher = _counter_fetcher()
    auth = Auth0M2MAuth(fetcher)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.test",
        auth=auth,
    ) as client:
        response = await client.get("/x")

    assert response.status_code == 401
    assert call_count["n"] == 2
    assert state["n"] == 2


@pytest.mark.anyio
async def test_auth_concurrent_first_requests_single_flight() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    state = {"n": 0}

    async def fetcher() -> str:
        state["n"] += 1
        await asyncio.sleep(0)
        return f"tok-{state['n']}"

    auth = Auth0M2MAuth(fetcher)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.test",
        auth=auth,
    ) as client:
        await asyncio.gather(*(client.get("/x") for _ in range(5)))

    assert state["n"] == 1


@pytest.mark.anyio
async def test_auth_non_401_does_not_trigger_refetch() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    state, fetcher = _counter_fetcher()
    auth = Auth0M2MAuth(fetcher)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.test",
        auth=auth,
    ) as client:
        response = await client.get("/x")

    assert response.status_code == 500
    assert state["n"] == 1


@pytest.mark.anyio
async def test_auth_concurrent_401s_refetch_once() -> None:
    """N in-flight requests that all 401 off one stale token → one refetch.

    Guards the single-flight fix: without stale-token double-checking, each of
    the N requests would force its own refetch (thundering herd).
    """
    seen_headers: list[str | None] = []

    def handler(req: httpx.Request) -> httpx.Response:
        auth = req.headers.get("Authorization")
        seen_headers.append(auth)
        # Only the very first token (tok-1) is rejected; the refetched token
        # (tok-2) is accepted.
        status = 401 if auth == "Bearer tok-1" else 200
        return httpx.Response(status, json={})

    state = {"n": 0}

    async def fetcher() -> str:
        state["n"] += 1
        await asyncio.sleep(0)
        return f"tok-{state['n']}"

    auth = Auth0M2MAuth(fetcher)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.test",
        auth=auth,
    ) as client:
        responses = await asyncio.gather(*(client.get("/x") for _ in range(5)))

    assert all(r.status_code == 200 for r in responses)
    # 1 initial fetch (tok-1) + exactly 1 refetch (tok-2), not 1-per-request.
    assert state["n"] == 2


# --- from_partial_env -------------------------------------------------------


def test_from_partial_env_returns_none_when_all_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_m2m_env(monkeypatch)

    assert (
        StitchClientConfig.from_partial_env(api_base_url="http://api.test/v1") is None
    )


def test_from_partial_env_returns_config_using_supplied_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_m2m_env(monkeypatch)
    for var in _M2M_VARS:
        monkeypatch.setenv(var, _ALL_VARS[var])
    # STITCH_API_BASE_URL is intentionally NOT read by from_partial_env.
    monkeypatch.setenv("STITCH_API_BASE_URL", "https://should-be-ignored.test")

    config = StitchClientConfig.from_partial_env(api_base_url="http://caller/api/v1")

    assert config is not None
    assert config.client_id == "cid"
    assert config.client_secret == "csec"
    assert config.audience == "https://api.test"
    assert config.auth_issuer_url == "https://issuer.test"
    assert config.api_base_url == "http://caller/api/v1"


def test_from_partial_env_raises_when_partially_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_m2m_env(monkeypatch)
    monkeypatch.setenv("STITCH_AUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("STITCH_AUTH_AUDIENCE", "https://api.test")

    with pytest.raises(StitchAuthError) as exc_info:
        StitchClientConfig.from_partial_env(api_base_url="http://api.test/v1")

    message = str(exc_info.value)
    assert "STITCH_AUTH_CLIENT_SECRET" in message
    assert "STITCH_AUTH_ISSUER_URL" in message


# --- validate_downstream_auth_at_startup ------------------------------------


@pytest.mark.anyio
async def test_validate_downstream_auth_noop_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_m2m_env(monkeypatch)

    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"access_token": "tok"})

    # No exception, and no token endpoint call (nothing to validate).
    await validate_downstream_auth_at_startup(
        api_base_url="http://api.test/v1",
        transport=httpx.MockTransport(handler),
    )
    assert calls["n"] == 0


@pytest.mark.anyio
async def test_validate_downstream_auth_raises_on_bad_creds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_m2m_env(monkeypatch)
    for var in _M2M_VARS:
        monkeypatch.setenv(var, _ALL_VARS[var])

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "access_denied"})

    with pytest.raises(StitchAuthError):
        await validate_downstream_auth_at_startup(
            api_base_url="http://api.test/v1",
            transport=httpx.MockTransport(handler),
        )


@pytest.mark.anyio
async def test_validate_downstream_auth_succeeds_with_valid_creds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_m2m_env(monkeypatch)
    for var in _M2M_VARS:
        monkeypatch.setenv(var, _ALL_VARS[var])

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "tok-abc"})

    await validate_downstream_auth_at_startup(
        api_base_url="http://api.test/v1",
        transport=httpx.MockTransport(handler),
    )
