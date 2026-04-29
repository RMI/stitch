from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from stitch.llm.entities import Citation
from stitch.llm.errors import AzureResponsesError, LLMConfigurationError
from stitch.llm.settings import Settings, get_settings
from stitch.llm.suggestions import AllowedSuggestionField, suggestion_response_schema


@dataclass(frozen=True, slots=True)
class AzureResponsesResult:
    output_text: str
    model: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    response_id: str | None = None


class AzureResponsesClient:
    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        if not self._settings.azure_openai_configured:
            raise LLMConfigurationError("Azure OpenAI settings are not configured.")

        assert self._settings.azure_openai_base_url is not None
        assert self._settings.azure_openai_api_key is not None
        assert self._settings.azure_openai_model is not None

        self._base_url = str(self._settings.azure_openai_base_url).rstrip("/")
        self._api_key = self._settings.azure_openai_api_key.get_secret_value()
        self._model = self._settings.azure_openai_model
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=self._settings.azure_openai_timeout_seconds,
        )

    async def __aenter__(self) -> "AzureResponsesClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def generate_field_suggestion(
        self,
        *,
        field: AllowedSuggestionField,
        input_messages: list[dict[str, str]],
    ) -> AzureResponsesResult:
        request_payload = {
            "model": self._model,
            "input": input_messages,
            "store": False,
            "tools": [{"type": "web_search"}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "oil_gas_field_suggestion",
                    "strict": True,
                    "schema": suggestion_response_schema(field),
                }
            },
        }
        try:
            response = await self._client.post(
                f"{self._base_url}/responses",
                headers={
                    "Content-Type": "application/json",
                    "api-key": self._api_key,
                },
                json=request_payload,
            )
        except httpx.HTTPError as exc:
            raise AzureResponsesError("Azure Responses request failed.") from exc

        if response.is_error:
            raise AzureResponsesError(
                f"Azure Responses request failed with status {response.status_code}: {response.text}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise AzureResponsesError(
                "Azure Responses returned non-JSON payload."
            ) from exc
        if body.get("error") is not None:
            raise AzureResponsesError("Azure Responses returned an error payload.")

        output_text = _extract_output_text(body)
        if output_text is None:
            raise AzureResponsesError("Azure Responses did not return output text.")

        return AzureResponsesResult(
            output_text=output_text,
            model=body.get("model") or self._model,
            request_payload=request_payload,
            response_payload=body,
            response_id=body.get("id"),
        )


def _extract_output_text(body: dict[str, Any]) -> str | None:
    output_text = body.get("output_text")
    if isinstance(output_text, str):
        return output_text

    output = body.get("output")
    if not isinstance(output, list):
        return None

    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            if content_item.get("type") in {"output_text", "text"}:
                text = content_item.get("text")
                if isinstance(text, str):
                    return text

    return None


def extract_public_citations(body: dict[str, Any]) -> list[Citation]:
    citations: list[Citation] = []
    seen: set[tuple[str, str | None]] = set()

    output = body.get("output")
    if not isinstance(output, list):
        return citations

    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            annotations = content_item.get("annotations")
            if not isinstance(annotations, list):
                continue
            for annotation in annotations:
                if not isinstance(annotation, dict):
                    continue
                if annotation.get("type") != "url_citation":
                    continue
                url = annotation.get("url")
                title = annotation.get("title")
                if not isinstance(url, str):
                    continue
                if not url.startswith(("http://", "https://")):
                    continue
                if title is not None and not isinstance(title, str):
                    title = None
                key = (url, title)
                if key in seen:
                    continue
                seen.add(key)
                citations.append(Citation(url=url, title=title))

    return citations
