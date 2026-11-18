from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

import stitch_core_llm
from stitch_core_llm import (
    get_llm_client,
    get_llm_settings,
    suggest_missing_field_values,
)
from stitch_core_llm.errors import (
    AzureResponsesError,
    LLMConfigurationError,
    ModelOutputError,
)
from stitch_core_llm.settings import LLMSettings

AZURE_ENV_VARS = (
    "STITCH_LLM_AZURE_OPENAI_BASE_URL",
    "STITCH_LLM_AZURE_OPENAI_API_KEY",
    "STITCH_LLM_AZURE_OPENAI_MODEL",
)


class Record(BaseModel):
    name: str | None = None
    basin: str | None = Field(default=None, description="The geological basin.")
    country: str | None = None


class SourceRow(BaseModel):
    source: str
    name: str | None = None


@dataclass
class Suggestable:
    data: Record
    source_data: list[SourceRow] = field(default_factory=list)
    suggestable_fields: tuple[str, ...] = ("name", "basin", "country")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch):
    for name in AZURE_ENV_VARS:
        monkeypatch.setenv(name, "")
    get_llm_settings.cache_clear()
    get_llm_client.cache_clear()
    yield
    get_llm_settings.cache_clear()
    get_llm_client.cache_clear()


def responses_body(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "resp_123",
        "object": "response",
        "created_at": 0,
        "model": "test-model",
        "status": "completed",
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "output": [
            {
                "type": "message",
                "id": "msg_123",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(payload),
                        "annotations": [],
                    }
                ],
            }
        ],
    }


def install_client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> list[dict[str, Any]]:
    monkeypatch.setenv("STITCH_LLM_AZURE_OPENAI_MODEL", "test-model")
    captured: list[dict[str, Any]] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return handler(request)

    client = AsyncOpenAI(
        base_url="https://example.openai.azure.com/openai/v1",
        api_key="azure-key",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(recording_handler)),
    )
    monkeypatch.setattr(stitch_core_llm, "get_llm_client", lambda: client)
    return captured


def model_reply(payload: dict[str, Any]) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(200, json=responses_body(payload))


def test_settings_treat_blank_values_as_unset() -> None:
    settings = LLMSettings(
        azure_openai_base_url="",
        azure_openai_api_key=" ",
        azure_openai_model="",
    )

    assert settings.azure_openai_base_url is None
    assert settings.azure_openai_api_key is None
    assert settings.azure_openai_model is None
    assert settings.azure_openai_configured is False


def test_get_llm_client_requires_azure_configuration() -> None:
    with pytest.raises(LLMConfigurationError):
        get_llm_client()


@pytest.mark.anyio
async def test_suggest_returns_cited_value(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = install_client(
        monkeypatch,
        model_reply(
            {
                "value": "Permian Basin",
                "rationale": "Public sources identify the basin.",
                "citations": [
                    {"url": "https://example.com/article", "title": "Example"}
                ],
            }
        ),
    )

    suggestions = await suggest_missing_field_values(
        resource_id=42,
        detail_view=Suggestable(data=Record(name="Alpha")),
        fields=["basin"],
    )

    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion.resource_id == 42
    assert suggestion.field == "basin"
    assert suggestion.value == "Permian Basin"
    assert suggestion.rationale == "Public sources identify the basin."
    assert [c.model_dump() for c in suggestion.citations] == [
        {"url": "https://example.com/article", "title": "Example"}
    ]
    assert suggestion.model == "test-model"
    assert suggestion.foundry_response["id"] == "resp_123"
    assert captured[0]["model"] == "test-model"
    assert captured[0]["tools"] == [{"type": "web_search"}]
    assert captured[0]["store"] is False
    assert "The geological basin." in captured[0]["instructions"]


@pytest.mark.anyio
async def test_suggest_drops_value_without_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_client(
        monkeypatch,
        model_reply(
            {
                "value": "Permian Basin",
                "rationale": "Recalled from memory.",
                "citations": [],
            }
        ),
    )

    [suggestion] = await suggest_missing_field_values(
        resource_id=42,
        detail_view=Suggestable(data=Record(name="Alpha")),
        fields=["basin"],
    )

    assert suggestion.value is None
    assert suggestion.citations == []


@pytest.mark.anyio
async def test_suggest_only_queries_missing_requested_suggestable_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = install_client(
        monkeypatch,
        model_reply({"value": None, "rationale": "No evidence.", "citations": []}),
    )

    suggestions = await suggest_missing_field_values(
        resource_id=42,
        detail_view=Suggestable(
            data=Record(name="Alpha"),
            suggestable_fields=("name", "basin"),
        ),
        fields=["name", "basin", "country"],
    )

    assert [suggestion.field for suggestion in suggestions] == ["basin"]
    assert len(captured) == 1


@pytest.mark.anyio
async def test_suggest_returns_empty_without_calling_model_when_nothing_is_missing() -> (
    None
):
    suggestions = await suggest_missing_field_values(
        resource_id=42,
        detail_view=Suggestable(data=Record(name="Alpha", basin="B", country="C")),
        fields=["name", "basin", "country"],
    )

    assert suggestions == []


@pytest.mark.anyio
async def test_suggest_wraps_request_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, lambda request: httpx.Response(500, json={}))

    with pytest.raises(AzureResponsesError):
        await suggest_missing_field_values(
            resource_id=42,
            detail_view=Suggestable(data=Record(name="Alpha")),
            fields=["basin"],
        )


@pytest.mark.anyio
async def test_suggest_rejects_output_that_does_not_match_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_client(monkeypatch, model_reply({"value": "Permian Basin"}))

    with pytest.raises(ModelOutputError):
        await suggest_missing_field_values(
            resource_id=42,
            detail_view=Suggestable(data=Record(name="Alpha")),
            fields=["basin"],
        )
