from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from .errors import StitchAPIError

logger = logging.getLogger("stitch.client")


class AsyncStitchClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 30.0,
        headers_provider: Callable[[], Mapping[str, str]] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._headers_provider = headers_provider
        if client is None:
            if base_url is None:
                raise ValueError("base_url is required when client is not provided")
            self._client = httpx.AsyncClient(
                base_url=base_url,
                timeout=timeout,
            )
            return

        if base_url is not None and self._normalize_base_url(
            client.base_url
        ) != self._normalize_base_url(base_url):
            raise ValueError("base_url does not match injected client base_url")

        self._client = client

    async def __aenter__(self) -> "AsyncStitchClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
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
                    headers=self._headers(),
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
            except (httpx.HTTPError, OSError) as exc:
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

    async def create_oil_gas_field(
        self,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        response_payload = await self._request_json(
            method="POST",
            path="/oil-gas-fields/",
            operation="POST /oil-gas-fields/",
            json=dict(payload),
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

    def _headers(self) -> dict[str, str]:
        if self._headers_provider is None:
            return {}
        return dict(self._headers_provider())

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
            headers=self._headers(),
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
    def _raise_for_status(response: httpx.Response, operation: str) -> None:
        if response.is_success:
            return
        raise StitchAPIError(
            f"{operation} failed with status {response.status_code}: {response.text}"
        )

    @staticmethod
    def _normalize_base_url(url: httpx.URL | str) -> str:
        return str(httpx.URL(str(url)).join("/"))
