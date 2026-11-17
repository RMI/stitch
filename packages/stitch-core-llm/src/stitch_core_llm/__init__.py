import asyncio
from collections.abc import Collection
from datetime import datetime, UTC
from pydantic import ValidationError
from pydantic.fields import FieldInfo
import json
from functools import lru_cache

from openai import AsyncOpenAI, OpenAIError

from .errors import LLMConfigurationError, AzureResponsesError, ModelOutputError
from .model import FieldSuggestion, SuggestedValue
from .settings import LLMSettings
from .typings import AllowedSuggestionField, AnyDetailView, ALL_SUGGESTION_FIELDS


@lru_cache
def get_llm_settings() -> LLMSettings:
    return LLMSettings()


@lru_cache
def get_llm_client() -> AsyncOpenAI:
    settings = get_llm_settings()
    if not settings.azure_openai_configured:
        raise LLMConfigurationError("Azure OpenAI settings are not configured.")
    assert settings.azure_openai_base_url is not None
    assert settings.azure_openai_api_key is not None
    return AsyncOpenAI(
        base_url=str(settings.azure_openai_base_url),
        api_key=settings.azure_openai_api_key.get_secret_value(),
        timeout=settings.azure_openai_timeout_seconds,
        max_retries=0,
    )


async def _suggest(
    *,
    client: AsyncOpenAI,
    resource_id: int,
    field: AllowedSuggestionField,
    detail_view: AnyDetailView,
    observed_at: datetime,
    info: dict[str, FieldInfo] | None = None,
) -> FieldSuggestion:
    description = info[field].description if info is not None else field
    coalesced = json.dumps(detail_view.data.model_dump(mode="json"))
    sources = json.dumps(
        [source.model_dump(mode="json") for source in detail_view.source_data]
    )
    try:
        response = await client.responses.parse(
            model=get_llm_settings().azure_openai_model or "",
            instructions=(
                f"You infer the `{field}` value for one oil and gas field. That field "
                f"means: {description} Search the public web for evidence and cite "
                f"every page you use. Return a null value unless a public citation "
                f"supports it. Infer no field other than `{field}`."
            ),
            input=(
                f"Coalesced Stitch record:\n{coalesced}\n\n"
                f"Source records behind it:\n{sources}"
            ),
            tools=[{"type": "web_search"}],
            text_format=SuggestedValue[FieldInfo],
            store=False,
        )
    except OpenAIError as exc:
        raise AzureResponsesError("Azure Responses request failed.") from exc
    except ValidationError as exc:
        raise ModelOutputError("Model output did not match the field schema.") from exc

    parsed = response.output_parsed
    if parsed is None:
        raise ModelOutputError("Model returned no parsed output.")

    cited = bool(parsed.citations)
    return FieldSuggestion(
        resource_id=resource_id,
        field=field,
        value=parsed.value if cited else None,
        citations=parsed.citations if cited else [],
        model=response.model,
        rationale=parsed.rationale,
        observed_at=observed_at,
        foundry_response=response.model_dump(mode="json"),
    )


async def suggest_missing_field_values(
    *,
    resource_id: int,
    detail_view: AnyDetailView,
    fields: Collection[AllowedSuggestionField] = ALL_SUGGESTION_FIELDS,
) -> list[FieldSuggestion]:

    requested = set(fields)
    targets = [
        field
        for field in ALL_SUGGESTION_FIELDS
        if field in requested and getattr(detail_view.data, field) is None
    ]
    if not targets:
        return []

    client = get_llm_client()
    observed_at = datetime.now(UTC)
    calls = [
        _suggest(
            client=client,
            resource_id=resource_id,
            field=field,
            detail_view=detail_view,
            observed_at=observed_at,
        )
        for field in targets
    ]
    return list(await asyncio.gather(*calls))
