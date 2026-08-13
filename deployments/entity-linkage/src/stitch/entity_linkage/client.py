from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from stitch.client import AsyncStitchClient, env_bearer_token_headers_provider

from stitch.entity_linkage.entities import FieldCandidate, FieldDetailCandidate
from stitch.entity_linkage.settings import get_settings

# Traffic class for the API's batch-yield gate, which makes batch callers wait
# while someone is actually using the app. The API owns this contract -- see
# ``TRAFFIC_CLASS_HEADER`` / ``BATCH_TRAFFIC_CLASS`` in ``stitch/api/admission.py``.
# Repeated as a literal rather than imported because neither deployable depends
# on the other, and a shared constant is not worth a new dependency edge for one
# string. If a second batch caller needs it (seed is the obvious candidate), lift
# it into ``stitch-client`` then.
TRAFFIC_CLASS_HEADER = "X-Stitch-Traffic-Class"
BATCH_TRAFFIC_CLASS = "batch"


def _get_api_base_url() -> str:
    """
    Resolve the downstream Stitch API base URL.
    """
    return str(get_settings().api_base_url)


def batch_headers_provider() -> Callable[[], dict[str, str]]:
    """Auth headers plus the batch traffic-class tag.

    Entity-linkage *is* batch traffic -- one long sequential pass over the whole
    dataset -- so it always volunteers to yield to interactive users. Nothing to
    configure: the tag is inert unless the API's gate is enabled, and requests are
    treated as interactive unless they downgrade themselves like this.
    """
    auth_headers = env_bearer_token_headers_provider()

    def provider() -> dict[str, str]:
        return {**auth_headers(), TRAFFIC_CLASS_HEADER: BATCH_TRAFFIC_CLASS}

    return provider


def validate_downstream_auth_config_at_startup() -> None:
    # Stays on the bare provider: this only checks that the token env var is set,
    # and the traffic-class tag has no configuration to validate.
    headers_provider = env_bearer_token_headers_provider()
    headers_provider()


class StitchApiClient:
    def __init__(
        self,
        client: AsyncStitchClient | None = None,
        *,
        tag_as_batch: bool = True,
    ):
        """
        ``tag_as_batch`` marks requests as deferrable batch work, which is right
        for the linkage pass but wrong for a readiness probe: a probe exists to
        report whether the API is reachable, so it must not be throttled by the
        very interactive traffic it is meant to be independent of. Callers that
        are just checking connectivity pass ``tag_as_batch=False``.
        """
        if client is not None:
            self._client = client
            return

        self._client = AsyncStitchClient(
            base_url=_get_api_base_url(),
            timeout=30.0,
            headers_provider=(
                batch_headers_provider()
                if tag_as_batch
                else env_bearer_token_headers_provider()
            ),
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
