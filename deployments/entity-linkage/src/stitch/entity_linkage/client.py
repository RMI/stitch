from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from stitch.client import AsyncStitchClient, env_bearer_token_headers_provider

from stitch.entity_linkage.entities import FieldCandidate, FieldDetailCandidate
from stitch.entity_linkage.settings import get_settings


def validate_downstream_auth_config_at_startup() -> None:
    headers_provider = env_bearer_token_headers_provider()
    headers_provider()


class StitchApiClient:
    def __init__(
        self,
        client: AsyncStitchClient | None = None,
    ):
        if client is not None:
            self._client = client
            return

        settings = get_settings()
        headers_provider = env_bearer_token_headers_provider()
        self._client = AsyncStitchClient(
            base_url=str(settings.api_base_url),
            timeout=settings.api_timeout_seconds,
            headers_provider=headers_provider,
            max_retries=settings.api_max_retries,
        )

    async def __aenter__(self) -> "StitchApiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def iter_oil_gas_fields(
        self,
        *,
        start_page: int = 1,
        page_size: int = 50,
        max_pages: int | None = None,
        q: str | None = None,
        name: str | None = None,
        country: str | None = None,
    ) -> AsyncIterator[FieldCandidate]:
        """Stream field candidates one page at a time (bounded memory)."""
        async for item in self._client.iter_oil_gas_fields(
            start_page=start_page,
            page_size=page_size,
            max_pages=max_pages,
            q=q,
            name=name,
            country=country,
        ):
            yield self._to_candidate(item)

    async def list_merge_candidates(self) -> list[dict[str, Any]]:
        return await self._client.list_merge_candidates()

    @staticmethod
    def _to_candidate(item: dict[str, Any]) -> FieldCandidate:
        data = item.get("data") or {}
        return FieldCandidate(
            id=item["id"],
            name=data.get("name"),
            country=data.get("country"),
        )

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
