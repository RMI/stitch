from __future__ import annotations

import httpx
import pytest

from stitch.client import AsyncStitchClient, STITCH_CLIENT_BEARER_TOKEN_ENV_VAR
from stitch.llm.client import StitchApiClient, validate_downstream_auth_config_at_startup
from stitch.llm.settings import Settings


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
    monkeypatch.setenv(STITCH_CLIENT_BEARER_TOKEN_ENV_VAR, "llm-token")
    settings = Settings(
        auth_disabled=True,
        api_base_url="http://injected.example/api/v1",
    )

    client = StitchApiClient(settings=settings)

    assert str(client._client._client.base_url) == "http://injected.example/api/v1/"
    await client.aclose()


def test_stitch_api_client_requires_env_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(STITCH_CLIENT_BEARER_TOKEN_ENV_VAR, raising=False)

    with pytest.raises(ValueError) as exc_info:
        validate_downstream_auth_config_at_startup()

    assert str(exc_info.value) == f"{STITCH_CLIENT_BEARER_TOKEN_ENV_VAR} must be set"
