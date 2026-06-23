from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from stitch.llm.azure_responses import AzureResponsesClient, extract_public_citations
from stitch.llm.client import StitchApiClient
from stitch.llm.entities import FieldSuggestionResponse
from stitch.llm.settings import get_settings
from stitch.llm.suggestions import (
    AllowedSuggestionField,
    build_field_suggestion_input,
    ensure_field_is_missing,
    is_string_suggestion_field,
    parse_field_suggestion_response,
    sanitize_and_validate_suggested_value,
)

PLACEHOLDER_LLM_VALUE = ":warning: placeholder LLM value"
PLACEHOLDER_LLM_MODEL = "placeholder-llm"


class FieldSuggestionParams(BaseModel):
    """Identifies the suggestion to run; also the dedup key (resource_id, field)."""

    resource_id: int
    field: AllowedSuggestionField


async def run_suggestion(params: FieldSuggestionParams) -> FieldSuggestionResponse:
    """Produce an LLM field suggestion as a background job.

    Domain failures (resource missing, field already populated, LLM config/output
    errors) propagate out and are captured by the JobManager as a failed record
    (observable via ``GET /status/{job_id}``) — there is no synchronous HTTP
    status mapping anymore.
    """
    resource_id = params.resource_id
    field = params.field
    observed_at = datetime.now(UTC)

    async with StitchApiClient() as stitch_client:
        detail_view = await stitch_client.get_oil_gas_field_detail(resource_id)

    # Expected behavior: if the field is already populated this raises and the
    # run is recorded as a failed job (surfaced in the UI as a failed run),
    # rather than the old synchronous 409. That's intentional — requesting a
    # suggestion for an already-filled field is a no-op the user can see.
    ensure_field_is_missing(detail_view, field)

    input_messages = build_field_suggestion_input(
        resource_id=resource_id,
        field=field,
        detail_view=detail_view,
    )
    settings = get_settings()

    if settings.auth_disabled and not settings.azure_openai_configured:
        fallback_value = (
            PLACEHOLDER_LLM_VALUE if is_string_suggestion_field(field) else None
        )
        return FieldSuggestionResponse(
            resource_id=resource_id,
            field=field,
            value=fallback_value,
            citations=[],
            query_succeeded=True,
            model=PLACEHOLDER_LLM_MODEL,
            rationale=(
                "Foundry is not configured in auth-disabled mode; returned a local "
                "placeholder value."
                if fallback_value is not None
                else "Foundry is not configured in auth-disabled mode; no safe "
                "placeholder exists for this field type."
            ),
            observed_at=observed_at,
            foundry_request={},
            foundry_response={},
        )

    async with AzureResponsesClient() as llm_client:
        llm_result = await llm_client.generate_field_suggestion(
            field=field,
            input_messages=input_messages,
        )
    parsed = parse_field_suggestion_response(llm_result.output_text)
    citations = extract_public_citations(llm_result.response_payload)
    if parsed.value is None or not citations:
        value = None
        citations = []
    else:
        value = sanitize_and_validate_suggested_value(
            detail_data=detail_view.data,
            field=field,
            value=parsed.value,
        )

    return FieldSuggestionResponse(
        resource_id=resource_id,
        field=field,
        value=value,
        citations=citations,
        query_succeeded=True,
        model=llm_result.model,
        rationale=parsed.rationale,
        observed_at=observed_at,
        foundry_request=llm_result.request_payload,
        foundry_response=llm_result.response_payload,
    )
