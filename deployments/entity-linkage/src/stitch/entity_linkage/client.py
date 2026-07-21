from __future__ import annotations

from typing import Any

from stitch.client import AsyncStitchClient

from stitch.entity_linkage.entities import FieldCandidate, FieldDetailCandidate
from stitch.entity_linkage.settings import get_settings


def _get_api_base_url() -> str:
    """
    Resolve the downstream Stitch API base URL.
    """
    return str(get_settings().api_base_url)


class StitchApiClient:
    def __init__(
        self,
        client: AsyncStitchClient | None = None,
    ):
        if client is not None:
            self._client = client
            return

        # Auth mode is selected by the environment: Auth0 M2M when the
        # STITCH_AUTH_* vars are present, otherwise no Authorization header
        # (local AUTH_DISABLED path).
        self._client = AsyncStitchClient.from_service_env(
            api_base_url=_get_api_base_url(),
            timeout=30.0,
        )

    async def __aenter__(self) -> "StitchApiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_oil_gas_fields_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        return await self._client.list_oil_gas_fields_page(
            page=page,
            page_size=page_size,
        )

    async def collect_oil_gas_fields(
        self,
        *,
        start_page: int = 1,
        page_size: int = 50,
        max_pages: int | None = None,
    ) -> tuple[list[FieldCandidate], int]:
        items, pages_fetched = await self._client.collect_oil_gas_fields(
            start_page=start_page,
            page_size=page_size,
            max_pages=max_pages,
        )
        return self._to_candidates(items), pages_fetched

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
        payload = await self._client.get_oil_gas_field_detail(resource_id)
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
        return await self._client.create_merge_candidate(resource_ids)

    async def get_auth_me(self) -> dict[str, Any]:
        return await self._client.get_auth_me()
