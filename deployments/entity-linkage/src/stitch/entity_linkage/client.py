from __future__ import annotations

from typing import Any

import httpx

from stitch.entity_linkage.entities import (
    FieldCandidate,
    FieldDetailCandidate,
    RequestAuthContext,
)
from stitch.entity_linkage.errors import StitchAPIError
from stitch.entity_linkage.settings import get_settings


def _get_api_base_url() -> str:
    """
    Resolve the downstream Stitch API base URL.
    """
    return str(get_settings().api_base_url)


class StitchApiClient:
    def __init__(self, auth_context: RequestAuthContext):
        self._auth_context = auth_context
        self._client = httpx.AsyncClient(
            base_url=_get_api_base_url(),
            timeout=30.0,
        )

    async def __aenter__(self) -> "StitchApiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._auth_context.bearer_token:
            headers["Authorization"] = f"Bearer {self._auth_context.bearer_token}"

        return headers

    async def list_oil_gas_fields_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        response = await self._client.get(
            "/oil-gas-fields/",
            params={"page": page, "page_size": page_size},
            headers=self._headers(),
        )
        self._raise_for_status(response, "GET /oil-gas-fields/")
        return response.json()

    async def collect_oil_gas_fields(
        self,
        *,
        start_page: int = 1,
        page_size: int = 50,
        max_pages: int | None = None,
    ) -> tuple[list[FieldCandidate], int]:
        items: list[FieldCandidate] = []
        pages_fetched = 0
        page = start_page

        while True:
            if max_pages is not None and pages_fetched >= max_pages:
                break

            payload = await self.list_oil_gas_fields_page(
                page=page,
                page_size=page_size,
            )
            page_items = self._extract_items(payload)
            pages_fetched += 1

            if not page_items:
                break

            items.extend(self._to_candidates(page_items))

            total_pages = payload.get("total_pages")
            if isinstance(total_pages, int) and page >= total_pages:
                break

            if len(page_items) < page_size:
                break

            page += 1

        return items, pages_fetched

    @staticmethod
    def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        items = payload.get("items")
        if isinstance(items, list):
            return items
        return []

    @staticmethod
    def _to_candidates(items: list[dict[str, Any]]) -> list[FieldCandidate]:
        candidates: list[FieldCandidate] = []
        for item in items:
            data = item.get("data") or {}
            candidates.append(
                FieldCandidate(
                    id=item["id"],
                    name=data.get("name"),
                    country=data.get("country"),
                )
            )
        return candidates

    async def get_oil_gas_field_detail(self, resource_id: int) -> FieldDetailCandidate:
        response = await self._client.get(
            f"/oil-gas-fields/{resource_id}/detail",
            headers=self._headers(),
        )
        self._raise_for_status(response, f"GET /oil-gas-fields/{resource_id}/detail")
        payload = response.json()
        data = payload.get("data") or {}
        return FieldDetailCandidate(
            id=payload["id"],
            name=data.get("name"),
            country=data.get("country"),
        )

    async def create_merge_candidate(
        self,
        *,
        resource_ids: list[int],
    ) -> dict[str, Any]:
        response = await self._client.post(
            "/oil-gas-fields/merge-candidates",
            json={"resource_ids": resource_ids},
            headers=self._headers(),
        )
        self._raise_for_status(response, "POST /oil-gas-fields/merge-candidates")
        return response.json()

    @staticmethod
    def _raise_for_status(response: httpx.Response, operation: str) -> None:
        if response.is_success:
            return
        raise StitchAPIError(
            f"{operation} failed with status {response.status_code}: {response.text}"
        )
