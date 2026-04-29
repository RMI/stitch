from __future__ import annotations

import json

import httpx
import pytest

from stitch.llm.errors import AzureResponsesError
from stitch.llm.azure_responses import AzureResponsesClient, _extract_output_text
from stitch.llm.settings import Settings


def make_settings() -> Settings:
    return Settings(
        auth_disabled=True,
        azure_openai_base_url="https://example.openai.azure.com/openai/v1",
        azure_openai_api_key="azure-key",
        azure_openai_model="test-model",
    )


def test_extract_output_text_prefers_shortcut_field() -> None:
    assert _extract_output_text({"output_text": '{"field":"basin","value":null}'}) == (
        '{"field":"basin","value":null}'
    )


def test_extract_output_text_falls_back_to_output_content() -> None:
    assert (
        _extract_output_text(
            {
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"field":"basin","value":"Permian"}',
                            }
                        ]
                    }
                ]
            }
        )
        == '{"field":"basin","value":"Permian"}'
    )


@pytest.mark.anyio
async def test_generate_field_suggestion_posts_responses_request() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["api_key"] = request.headers.get("api-key")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "id": "resp_123",
                "model": "test-model",
                "output_text": '{"field":"basin","value":"Permian"}',
            },
        )

    raw_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AzureResponsesClient(settings=make_settings(), client=raw_client)

    result = await client.generate_field_suggestion(
        field="basin",
        input_messages=[{"role": "user", "content": "payload"}],
    )

    assert result.output_text == '{"field":"basin","value":"Permian"}'
    assert result.model == "test-model"
    assert result.response_id == "resp_123"
    assert captured["method"] == "POST"
    assert captured["path"] == "/openai/v1/responses"
    assert captured["api_key"] == "azure-key"
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["text"]["format"]["type"] == "json_schema"

    await raw_client.aclose()


@pytest.mark.anyio
async def test_generate_field_suggestion_wraps_non_json_payload() -> None:
    raw_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="not-json")
        )
    )
    client = AzureResponsesClient(settings=make_settings(), client=raw_client)

    with pytest.raises(AzureResponsesError):
        await client.generate_field_suggestion(
            field="basin",
            input_messages=[{"role": "user", "content": "payload"}],
        )

    await raw_client.aclose()
