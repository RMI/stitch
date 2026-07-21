from __future__ import annotations

import httpx
import pytest

from stitch.client import AsyncStitchClient, Auth0M2MAuth, StitchAuthError
from stitch.llm.client import StitchApiClient
from stitch.llm.settings import Settings

_M2M_VARS = {
    "STITCH_AUTH_CLIENT_ID": "cid",
    "STITCH_AUTH_CLIENT_SECRET": "csec",
    "STITCH_AUTH_AUDIENCE": "https://api.test",
    "STITCH_AUTH_ISSUER_URL": "https://issuer.test",
}


def _clear_m2m_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (*_M2M_VARS, "STITCH_API_BASE_URL"):
        monkeypatch.delenv(var, raising=False)


def test_settings_treat_blank_optional_values_as_unset() -> None:
    settings = Settings(
        auth_disabled=True,
        azure_openai_base_url="",
        azure_openai_api_key="",
        azure_openai_model="",
    )

    assert settings.azure_openai_base_url is None
    assert settings.azure_openai_api_key is None
    assert settings.azure_openai_model is None
    assert settings.azure_openai_configured is False


@pytest.mark.anyio
async def test_stitch_api_client_validates_detail_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": 42,
                "data": {"name": "Alpha", "country": "USA", "basin": None},
                "provenance": {},
                "source_data": [{"source": "gem", "name": "Alpha", "country": "USA"}],
            },
        )

    raw_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://example.test/api/v1",
    )
    client = StitchApiClient(
        client=AsyncStitchClient(client=raw_client),
        settings=Settings(auth_disabled=True),
    )

    detail_view = await client.get_oil_gas_field_detail(42)

    assert detail_view.id == 42
    assert detail_view.data.name == "Alpha"
    assert detail_view.data.basin is None

    await raw_client.aclose()


@pytest.mark.anyio
async def test_stitch_api_client_uses_injected_settings_for_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_m2m_env(monkeypatch)
    settings = Settings(
        auth_disabled=True,
        api_base_url="http://injected.example/api/v1",
    )

    client = StitchApiClient(settings=settings)

    assert str(client._client._client.base_url) == "http://injected.example/api/v1/"
    assert client._client._client.auth is None
    await client.aclose()


@pytest.mark.anyio
async def test_stitch_api_client_uses_m2m_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_m2m_env(monkeypatch)
    for var, value in _M2M_VARS.items():
        monkeypatch.setenv(var, value)

    client = StitchApiClient(settings=Settings(auth_disabled=False))
    try:
        assert isinstance(client._client._client.auth, Auth0M2MAuth)
    finally:
        await client.aclose()


def test_stitch_api_client_partial_m2m_config_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_m2m_env(monkeypatch)
    monkeypatch.setenv("STITCH_AUTH_CLIENT_ID", "cid")

    with pytest.raises(StitchAuthError):
        StitchApiClient(settings=Settings(auth_disabled=False))
