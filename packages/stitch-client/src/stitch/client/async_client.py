from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import httpx
from stitch.ogsi.model import OGFieldResource

from .errors import StitchAPIError, StitchAuthError

if TYPE_CHECKING:
    from .config import StitchClientConfig

logger = logging.getLogger("stitch.client")


class AsyncStitchClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = client is None
        if client is not None:
            if base_url is not None:
                raise ValueError(
                    "base_url cannot be provided when client is already configured"
                )
            if timeout is not None:
                raise ValueError(
                    "timeout cannot be provided when client is already configured"
                )
            self._client = client
            return

        if base_url is None:
            raise ValueError("base_url is required when client is not provided")

        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout if timeout is not None else 30.0,
        )

    @classmethod
    def from_config(
        cls,
        config: "StitchClientConfig",
        *,
        timeout: float = 30.0,
    ) -> "AsyncStitchClient":
        from .auth import Auth0M2MAuth, fetch_auth_jwt

        async def _fetch() -> str:
            return await fetch_auth_jwt(config)

        httpx_client = httpx.AsyncClient(
            base_url=config.api_base_url,
            timeout=timeout,
            auth=Auth0M2MAuth(_fetch),
        )
        instance = cls(client=httpx_client)
        instance._owns_client = True
        return instance

    @classmethod
    def from_env(cls, *, timeout: float = 30.0) -> "AsyncStitchClient":
        from .config import StitchClientConfig

        return cls.from_config(StitchClientConfig.from_env(), timeout=timeout)

    @classmethod
    def from_service_env(
        cls,
        *,
        api_base_url: str,
        timeout: float = 30.0,
    ) -> "AsyncStitchClient":
        """Build a client whose auth mode is selected by the environment.

        This is what deployed services call. It uses the service's own base-url
        (passed in), not ``STITCH_API_BASE_URL``:

        - When the four ``STITCH_AUTH_*`` vars are present, returns an
          Auth0 M2M client (short-lived tokens fetched on demand).
        - When they are all absent, returns a plain client that attaches no
          ``Authorization`` header (the local ``AUTH_DISABLED`` path).
        - A partially-set M2M config raises ``StitchAuthError`` (fail loud).
        """
        from .config import StitchClientConfig

        config = StitchClientConfig.from_partial_env(api_base_url=api_base_url)
        if config is not None:
            return cls.from_config(config, timeout=timeout)
        return cls(base_url=api_base_url, timeout=timeout)

    async def __aenter__(self) -> "AsyncStitchClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def wait_for_health(
        self,
        retries: int = 30,
        delay: float = 2.0,
        request_timeout: float = 2.0,
    ) -> None:
        operation = "GET /health"

        for attempt in range(1, retries + 1):
            try:
                response = await self._client.get(
                    "/health",
                    timeout=request_timeout,
                )
                if response.is_success:
                    logger.info("API ready after %s attempt(s)", attempt)
                    return

                logger.info(
                    "API not ready (status %s), attempt %s of %s",
                    response.status_code,
                    attempt,
                    retries,
                )
            except (httpx.HTTPError, OSError, StitchAuthError) as exc:
                # StitchAuthError: in the live-M2M posture the client's auth
                # attaches a token even to the (unauthenticated) /health probe,
                # so a transient Auth0 blip must be retried, not treated as a
                # hard failure that aborts with zero retries.
                logger.info(
                    "API not reachable (%s), attempt %s/%s",
                    exc,
                    attempt,
                    retries,
                )

            if attempt < retries:
                await asyncio.sleep(delay)

        raise RuntimeError(f"{operation} did not become ready in time")

    async def list_oil_gas_fields_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        payload = await self._request_json(
            method="GET",
            path="/oil-gas-fields/",
            operation="GET /oil-gas-fields/",
            params={"page": page, "page_size": page_size},
        )
        return self._expect_dict(payload, "GET /oil-gas-fields/")

    async def collect_oil_gas_fields(
        self,
        *,
        start_page: int = 1,
        page_size: int = 50,
        max_pages: int | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        items: list[dict[str, Any]] = []
        pages_fetched = 0
        page = start_page

        while True:
            if max_pages is not None and pages_fetched >= max_pages:
                break

            payload = await self.list_oil_gas_fields_page(
                page=page,
                page_size=page_size,
            )
            raw_item_count = self._item_count(payload)
            page_items = self._extract_items(payload)
            pages_fetched += 1

            if raw_item_count == 0:
                break

            items.extend(page_items)

            total_pages = payload.get("total_pages")
            if isinstance(total_pages, int) and page >= total_pages:
                break

            if not isinstance(total_pages, int) and not page_items:
                break

            if raw_item_count < page_size:
                break

            page += 1

        return items, pages_fetched

    async def get_oil_gas_field_detail(self, resource_id: int) -> dict[str, Any]:
        payload = await self._request_json(
            method="GET",
            path=f"/oil-gas-fields/{resource_id}/detail",
            operation=f"GET /oil-gas-fields/{resource_id}/detail",
        )
        return self._expect_dict(payload, f"GET /oil-gas-fields/{resource_id}/detail")

    async def get_auth_me(self) -> dict[str, Any]:
        payload = await self._request_json(
            method="GET",
            path="/auth/me",
            operation="GET /auth/me",
        )
        return self._expect_dict(payload, "GET /auth/me")

    async def create_oil_gas_field(
        self,
        payload: OGFieldResource | Mapping[str, Any],
    ) -> dict[str, Any]:
        validated_payload = self._validate_oil_gas_field_payload(payload)
        response_payload = await self._request_json(
            method="POST",
            path="/oil-gas-fields/",
            operation="POST /oil-gas-fields/",
            json=validated_payload.model_dump(mode="json", exclude_unset=True),
        )
        return self._expect_dict(response_payload, "POST /oil-gas-fields/")

    async def create_merge_candidate(self, resource_ids: list[int]) -> dict[str, Any]:
        payload = await self._request_json(
            method="POST",
            path="/oil-gas-fields/merge-candidates",
            operation="POST /oil-gas-fields/merge-candidates",
            json={"resource_ids": resource_ids},
        )
        return self._expect_dict(payload, "POST /oil-gas-fields/merge-candidates")

    async def _request_json(
        self,
        *,
        method: str,
        path: str,
        operation: str,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> Any:
        response = await self._client.request(
            method,
            path,
            params=params,
            json=json,
        )
        self._raise_for_status(response, operation)
        return response.json()

    @staticmethod
    def _expect_dict(payload: Any, operation: str) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        raise StitchAPIError(f"{operation} returned non-object JSON payload")

    @staticmethod
    def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        items = payload.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        return []

    @staticmethod
    def _item_count(payload: dict[str, Any]) -> int:
        items = payload.get("items")
        if isinstance(items, list):
            return len(items)
        return 0

    @staticmethod
    def _validate_oil_gas_field_payload(
        payload: OGFieldResource | Mapping[str, Any],
    ) -> OGFieldResource:
        if isinstance(payload, OGFieldResource):
            return payload
        return OGFieldResource.model_validate(payload)

    @staticmethod
    def _raise_for_status(response: httpx.Response, operation: str) -> None:
        if response.is_success:
            return
        raise StitchAPIError(
            f"{operation} failed with status {response.status_code}: {response.text}",
            status_code=response.status_code,
            response_text=response.text,
        )
