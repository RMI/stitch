import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
import httpx

from stitch.api.entities import (
    OGFieldQueryParams,
    PaginatedResponse,
)

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db.config import UnitOfWorkDep
from stitch.api.auth import CurrentUser
from stitch.api.db.utils import (
    resource_to_view,
    resource_to_detail_view,
)
from stitch.api.llm_suggestions import (
    AzureOpenAILLMSuggestionClient,
    LLMFieldSuggestionRequest,
    LLMFieldSuggestionResponse,
    build_llm_suggestion_messages,
    parse_llm_suggestion_response,
    validate_llm_suggestion_field,
)
from stitch.api.settings import Settings, get_settings

from stitch.ogsi.model import (
    OGFieldDetailView,
    OGFieldListItemView,
    OGFieldResource,
    OGFieldView,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/oil-gas-fields",
    tags=["oil_gas_fields"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_all_resources(
    *,
    uow: UnitOfWorkDep,
    _user: CurrentUser,
    params: Annotated[OGFieldQueryParams, Query()],
) -> PaginatedResponse[OGFieldListItemView]:
    items, total_count = await resource_actions.query(
        session=uow.session, params=params
    )
    return PaginatedResponse(
        items=items,
        total_count=total_count,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{id}", response_model=OGFieldView)
async def get_resource(
    *, uow: UnitOfWorkDep, user: CurrentUser, id: int
) -> OGFieldView:
    res: OGFieldResource = await resource_actions.get(session=uow.session, id=id)
    return resource_to_view(resource=res)


@router.get("/{id}/detail", response_model=OGFieldDetailView)
async def get_resource_detail(
    *, uow: UnitOfWorkDep, user: CurrentUser, id: int
) -> OGFieldDetailView:
    res: OGFieldResource = await resource_actions.get(session=uow.session, id=id)
    return resource_to_detail_view(resource=res)


@router.post("/{id}/llm-suggestions", response_model=LLMFieldSuggestionResponse)
async def create_llm_suggestion(
    *,
    uow: UnitOfWorkDep,
    _user: CurrentUser,
    settings: Settings = Depends(get_settings),
    id: int,
    request: LLMFieldSuggestionRequest,
) -> LLMFieldSuggestionResponse:
    if not settings.llm_suggestions_configured:
        raise HTTPException(
            status_code=503, detail="LLM suggestions are not configured."
        )

    try:
        validate_llm_suggestion_field(request.field)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    resource = await resource_actions.get(session=uow.session, id=id)
    detail_view = resource_to_detail_view(resource=resource)
    messages = build_llm_suggestion_messages(
        resource_id=id,
        field_name=request.field,
        detail_view=detail_view,
    )

    try:
        client = AzureOpenAILLMSuggestionClient(settings)
        raw_response = await client.generate_field_suggestion(messages=messages)
        suggestion = parse_llm_suggestion_response(
            raw_response, requested_field=request.field
        )
    except httpx.HTTPError as exc:
        logger.exception(
            "Azure OpenAI request failed for resource %s field %s", id, request.field
        )
        raise HTTPException(
            status_code=502, detail="Failed to generate LLM suggestion."
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return LLMFieldSuggestionResponse(
        resource_id=id,
        field=request.field,
        suggested_value=suggestion.value,
        raw_response=raw_response,
    )


@router.post("/", response_model=OGFieldResource)
async def create_resource(
    *, uow: UnitOfWorkDep, user: CurrentUser, resource_in: OGFieldResource
) -> OGFieldResource:
    return await resource_actions.create(
        session=uow.session, user=user, resource=resource_in
    )


@router.post("/merge", response_model=OGFieldResource)
async def merge_resources_endpoint(
    *, uow: UnitOfWorkDep, user: CurrentUser, resource_ids: list[int]
) -> OGFieldResource:
    """
    Merge multiple resources into one (STUB):
    repoint resource_ids[1:] -> resource_ids[0]
    """
    # preserve order but drop duplicates
    unique_ids = list(dict.fromkeys(resource_ids))
    if len(unique_ids) < 2:
        raise HTTPException(
            status_code=400, detail="Provide at least 2 unique resource IDs"
        )

    logger.info(
        "Merge requested by user=%s for resource_ids=%s",
        getattr(user, "sub", "<anon>"),
        unique_ids,
    )

    try:
        return await resource_actions.merge_resources(
            session=uow.session,
            user=user,
            resource_ids=unique_ids,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error while merging resources %s: %s", unique_ids, exc)
        raise HTTPException(status_code=500, detail="Internal error during merge")
