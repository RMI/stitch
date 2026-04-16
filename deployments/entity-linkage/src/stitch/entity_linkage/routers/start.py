from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.status import HTTP_502_BAD_GATEWAY

from stitch.entity_linkage.auth import AuthContext
from stitch.entity_linkage.client import StitchApiClient
from stitch.entity_linkage.entities import FieldCandidate, MatchGroup, User
from stitch.entity_linkage.errors import StitchAPIError

router = APIRouter(tags=["entity-linkage"])


class StartRequest(BaseModel):
    apply_merges: bool = Field(
        default=False,
        description=(
            "When true, submit confirmed match groups to the Stitch API as "
            "merge candidates."
        ),
    )
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    max_pages: int | None = Field(
        default=None,
        ge=1,
        le=1000,
        description="Optional cap on pages fetched. Null means fetch all pages.",
    )


class StartResponse(BaseModel):
    initiated_by: str
    apply_merges: bool
    relay_mode: str
    pages_fetched: int
    total_records_fetched: int
    duplicate_name_candidate_count: int
    detail_records_fetched: int
    match_groups: list[list[int]]
    merge_results: list[dict]


def _extract_user_label(user: User) -> str:
    return user.name or user.email or user.sub


def _group_duplicate_names(
    items: list[FieldCandidate],
) -> dict[str, list[FieldCandidate]]:
    grouped: dict[str, list[FieldCandidate]] = defaultdict(list)
    for item in items:
        if item.normalized_name is None:
            continue
        grouped[item.normalized_name].append(item)
    return {
        normalized_name: grouped_items
        for normalized_name, grouped_items in grouped.items()
        if len(grouped_items) > 1
    }


def _normalize_country(country: str | None) -> str | None:
    if country is None:
        return None
    normalized = country.strip().upper()
    return normalized or None


async def _resolve_match_groups(
    client: StitchApiClient,
    duplicate_groups: dict[str, list[FieldCandidate]],
) -> tuple[list[MatchGroup], int]:
    match_groups: list[MatchGroup] = []
    detail_records_fetched = 0

    for normalized_name, candidates in duplicate_groups.items():
        by_country: dict[str, list[int]] = defaultdict(list)

        for candidate in candidates:
            detail = await client.get_oil_gas_field_detail(candidate.id)
            detail_records_fetched += 1
            normalized_country = _normalize_country(detail.country)
            if normalized_country is None:
                continue
            by_country[normalized_country].append(detail.id)

        for country, ids in by_country.items():
            if len(ids) > 1:
                match_groups.append(
                    MatchGroup(
                        ids=sorted(ids),
                        normalized_name=normalized_name,
                        country=country,
                    )
                )

    return match_groups, detail_records_fetched


@router.post("/start", response_model=StartResponse)
async def start(
    request: StartRequest,
    auth_context: AuthContext,
) -> StartResponse:
    """
    In-memory entity-linkage pass:
    - fetch paginated oil-gas-fields list
    - group exact case-insensitive duplicate names
    - fetch detail records for candidate duplicates
    - confirm same-country matches
    - optionally submit merge candidates

    Not implemented:
    - add concurrency controls for detail fetches
    - add stronger second-phase inspection beyond country equality
    - add machine/OBO auth for downstream API calls
    """
    try:
        async with StitchApiClient(auth_context=auth_context) as client:
            items, pages_fetched = await client.collect_oil_gas_fields(
                start_page=request.page,
                page_size=request.page_size,
                max_pages=request.max_pages,
            )
            duplicate_groups = _group_duplicate_names(items)
            match_groups, detail_records_fetched = await _resolve_match_groups(
                client=client,
                duplicate_groups=duplicate_groups,
            )

            merge_results: list[dict] = []
            if request.apply_merges:
                for group in match_groups:
                    response = await client.create_merge_candidate(
                        resource_ids=group.ids
                    )
                    merge_results.append(
                        {
                            "ids": group.ids,
                            "response": response,
                        }
                    )
    except StitchAPIError as exc:
        raise HTTPException(
            status_code=HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return StartResponse(
        initiated_by=_extract_user_label(auth_context.user),
        apply_merges=request.apply_merges,
        relay_mode="transparent",
        pages_fetched=pages_fetched,
        total_records_fetched=len(items),
        duplicate_name_candidate_count=sum(
            len(group) for group in duplicate_groups.values()
        ),
        detail_records_fetched=detail_records_fetched,
        match_groups=[group.ids for group in match_groups],
        merge_results=merge_results,
    )
