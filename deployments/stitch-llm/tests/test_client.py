from __future__ import annotations

import httpx
import pytest

from stitch.client import AsyncStitchClient
from stitch.llm.client import StitchApiClient, downstream_auth_headers
from stitch.llm.errors import LLMConfigurationError
from stitch.llm.settings import Settings


def test_downstream_auth_headers_uses_placeholder_when_auth_disabled() -> None:
    settings = Settings(
        auth_disabled=True,
        azure_openai_base_url="https://example.openai.azure.com/openai/v1",
        azure_openai_api_key="azure-key",
        azure_openai_model="model",
    )

    assert downstream_auth_headers(settings) == {
        "Authorization": "Bearer dev-placeholder-token"
    }


def test_downstream_auth_headers_uses_machine_token_when_auth_enabled() -> None:
    settings = Settings(
        auth_disabled=False,
        machine_token="machine-token",
        azure_openai_base_url="https://example.openai.azure.com/openai/v1",
        azure_openai_api_key="azure-key",
        azure_openai_model="model",
    )

    assert downstream_auth_headers(settings) == {
        "Authorization": "Bearer machine-token"
    }


def test_downstream_auth_headers_requires_machine_token_when_auth_enabled() -> None:
    settings = Settings(
        auth_disabled=False,
        machine_token=None,
        azure_openai_base_url="https://example.openai.azure.com/openai/v1",
        azure_openai_api_key="azure-key",
        azure_openai_model="model",
    )

    with pytest.raises(LLMConfigurationError):
        downstream_auth_headers(settings)


def test_settings_treat_blank_optional_values_as_unset() -> None:
    settings = Settings(
        auth_disabled=True,
        machine_token="",
        azure_openai_base_url="",
        azure_openai_api_key="",
        azure_openai_model="",
    )

    assert settings.machine_token is None
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


def test_stitch_api_client_uses_injected_settings_for_base_url() -> None:
    settings = Settings(
        auth_disabled=True,
        api_base_url="http://injected.example/api/v1",
    )

    client = StitchApiClient(settings=settings)

    assert str(client._client._client.base_url) == "http://injected.example/api/v1/"
