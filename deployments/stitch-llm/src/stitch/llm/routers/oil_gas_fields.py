from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.status import (
    HTTP_404_NOT_FOUND,
    HTTP_502_BAD_GATEWAY,
    HTTP_503_SERVICE_UNAVAILABLE,
)
from stitch.client import StitchAPIError
from stitch.auth.permissions import SERVICE_LLM_SUGGEST

from stitch.llm.auth import CurrentUser, require_permissions
from stitch.llm.azure_responses import AzureResponsesClient, extract_public_citations
from stitch.llm.client import StitchApiClient
from stitch.llm.entities import FieldSuggestionResponse
from stitch.llm.errors import (
    AzureResponsesError,
    LLMConfigurationError,
    ModelOutputError,
)
from stitch.llm.suggestions import (
    AllowedSuggestionField,
    build_field_suggestion_input,
    is_string_suggestion_field,
    parse_field_suggestion_response,
    sanitize_and_validate_suggested_value,
)
from stitch.llm.settings import get_settings

logger = logging.getLogger(__name__)

PLACEHOLDER_LLM_VALUE = ":warning: placeholder LLM value"
PLACEHOLDER_LLM_MODEL = "placeholder-llm"

router = APIRouter(
    prefix="/oil-gas-fields",
    tags=["oil_gas_fields"],
    responses={404: {"description": "Not found"}},
)


@router.get(
    "/{id}",
    response_model=FieldSuggestionResponse,
    dependencies=[Depends(require_permissions(SERVICE_LLM_SUGGEST))],
)
async def suggest_oil_gas_field_value(
    *,
    _user: CurrentUser,
    id: int,
    field: Annotated[AllowedSuggestionField, Query()],
) -> FieldSuggestionResponse:
    observed_at = datetime.now(UTC)
    try:
        async with StitchApiClient() as stitch_client:
            detail_view = await stitch_client.get_oil_gas_field_detail(id)
    except StitchAPIError as exc:
        if exc.status_code == HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        logger.exception("Stitch API request failed for resource %s", id)
        raise HTTPException(
            status_code=HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch resource detail from Stitch API.",
        ) from exc
    except LLMConfigurationError as exc:
        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ModelOutputError as exc:
        raise HTTPException(
            status_code=HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    input_messages = build_field_suggestion_input(
        resource_id=id,
        field=field,
        detail_view=detail_view,
    )
    settings = get_settings()

    if settings.auth_disabled and not settings.azure_openai_configured:
        fallback_value = (
            PLACEHOLDER_LLM_VALUE if is_string_suggestion_field(field) else None
        )
        return FieldSuggestionResponse(
            resource_id=id,
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

    try:
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
    except LLMConfigurationError as exc:
        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except (AzureResponsesError, ModelOutputError) as exc:
        raise HTTPException(
            status_code=HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return FieldSuggestionResponse(
        resource_id=id,
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
