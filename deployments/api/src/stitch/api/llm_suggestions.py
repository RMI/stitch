import json
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from stitch.api.settings import Settings
from stitch.ogsi.model import OGFieldDetailView
from stitch.ogsi.model.og_field import OilGasFieldBase


ALLOWED_LLM_SUGGESTION_FIELDS = (
    "basin",
    "state_province",
    "discovery_year",
    "fid_year",
    "production_start_year",
    "location_type",
    "field_status",
    "primary_hydrocarbon_group",
    "production_conventionality",
)


class LLMFieldSuggestionRequest(BaseModel):
    field: str


class LLMFieldSuggestionResponse(BaseModel):
    resource_id: int
    field: str
    suggested_value: Any
    raw_response: str


class ParsedLLMFieldSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: Any


def validate_llm_suggestion_field(field_name: str) -> None:
    if field_name not in ALLOWED_LLM_SUGGESTION_FIELDS:
        raise ValueError(f"Field `{field_name}` is not enabled for LLM suggestions.")


def build_llm_suggestion_messages(
    *,
    resource_id: int,
    field_name: str,
    detail_view: OGFieldDetailView,
) -> list[dict[str, str]]:
    validate_llm_suggestion_field(field_name)

    field_info = OilGasFieldBase.model_fields[field_name]
    field_description = field_info.description or field_name.replace("_", " ")
    coalesced_data = detail_view.data.model_dump(mode="json")
    source_records = [
        source.model_dump(mode="json") for source in detail_view.source_data
    ]

    return [
        {
            "role": "system",
            "content": (
                "You infer one field for an oil and gas field record from provided data only. "
                "Reply with JSON only. "
                'Return exactly these keys: "name", "value". '
                "Never use outside knowledge. "
                "Do not include markdown fences or extra explanation."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "Infer a single field value from the provided record context.",
                    "resource_id": resource_id,
                    "field_name": field_name,
                    "field_description": field_description,
                    "instructions": [
                        "Infer only the requested field.",
                        "Set name to the requested field name exactly.",
                        "Use only the provided coalesced resource and source records.",
                        "Do not use outside knowledge.",
                        "Use null for value if the field cannot be inferred.",
                    ],
                    "coalesced_resource": coalesced_data,
                    "source_records": source_records,
                },
                indent=2,
            ),
        },
    ]


def parse_llm_suggestion_response(
    raw_response: str, *, requested_field: str
) -> ParsedLLMFieldSuggestion:
    try:
        payload = json.loads(_strip_code_fences(raw_response))
        parsed = ParsedLLMFieldSuggestion.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("Model did not return valid suggestion JSON.") from exc

    if parsed.name != requested_field:
        raise ValueError("Model returned a suggestion for the wrong field.")

    return parsed


def _strip_code_fences(raw_response: str) -> str:
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


class AzureOpenAILLMSuggestionClient:
    def __init__(self, settings: Settings):
        if not settings.llm_suggestions_configured:
            raise ValueError("Azure OpenAI settings are not configured.")

        api_key = settings.azure_openai_api_key
        endpoint = settings.azure_openai_endpoint
        deployment = settings.azure_openai_deployment
        api_version = settings.azure_openai_api_version

        assert api_key is not None
        assert endpoint is not None
        assert deployment is not None
        assert api_version is not None

        self._api_key = api_key.get_secret_value()
        self._endpoint = str(endpoint).rstrip("/")
        self._deployment = deployment
        self._api_version = api_version

    async def generate_field_suggestion(self, *, messages: list[dict[str, str]]) -> str:
        url = f"{self._endpoint}/openai/deployments/{self._deployment}/chat/completions"
        params = {"api-version": self._api_version}
        headers = {"api-key": self._api_key, "Content-Type": "application/json"}
        payload = {
            "messages": messages,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                params=params,
                headers=headers,
                json=payload,
            )
            if response.is_error:
                raise httpx.HTTPStatusError(
                    f"Azure OpenAI request failed with status {response.status_code}: {response.text}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            body = response.json()

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(
                "Azure OpenAI response did not contain message content."
            ) from exc
