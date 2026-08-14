from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any

import httpx
from stitch.ogsi.model import OGFieldResource, OGSISrcKey

from .errors import StitchAPIError

logger = logging.getLogger("stitch.client")

MAX_PAGE_SIZE = 200
"""Server cap on ``page_size`` (``PaginationParams.page_size`` is ``Field(50, ge=1, le=200)``)."""


class AsyncStitchClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float | None = None,
        headers_provider: Callable[[], Mapping[str, str]] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._headers_provider = headers_provider
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
        q: str | None = None,
        name: str | None = None,
        country: str | None = None,
    ) -> dict[str, Any]:
        """One page of Oil & Gas Field resources.

        Raises:
            ValueError: if ``page``/``page_size`` are out of range.
            StitchAPIError: on a non-2xx response.
        """
        self._validate_page_params(page, page_size)
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if q is not None:
            params["q"] = q
        if name is not None:
            params["name"] = name
        if country is not None:
            params["country"] = country
        payload = await self._request_json(
            method="GET",
            path="/oil-gas-fields/",
            operation="GET /oil-gas-fields/",
            params=params,
        )
        return self._expect_dict(payload, "GET /oil-gas-fields/")

    async def iter_oil_gas_fields(
        self,
        *,
        start_page: int = 1,
        page_size: int = 50,
        max_pages: int | None = None,
        q: str | None = None,
        name: str | None = None,
        country: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield oil-gas-field items one page at a time.

        Bounded-memory counterpart to :meth:`collect_oil_gas_fields`: only a
        single page is held in memory at once, so callers can stream the whole
        result set without materializing it. Page-termination logic mirrors
        ``collect_oil_gas_fields``.
        """
        pages_fetched = 0
        page = start_page

        while True:
            if max_pages is not None and pages_fetched >= max_pages:
                return

            payload = await self.list_oil_gas_fields_page(
                page=page,
                page_size=page_size,
                q=q,
                name=name,
                country=country,
            )
            raw_item_count = self._item_count(payload)
            page_items = self._extract_items(payload)
            pages_fetched += 1

            if raw_item_count == 0:
                return

            for item in page_items:
                yield item

            total_pages = payload.get("total_pages")
            if isinstance(total_pages, int) and page >= total_pages:
                return

            if not isinstance(total_pages, int) and not page_items:
                return

            if raw_item_count < page_size:
                return

            page += 1

    async def collect_oil_gas_fields(
        self,
        *,
        start_page: int = 1,
        page_size: int = 50,
        max_pages: int | None = None,
        q: str | None = None,
        name: str | None = None,
        country: str | None = None,
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
                q=q,
                name=name,
                country=country,
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

    async def list_oil_gas_field_sources_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        source: Sequence[OGSISrcKey] | None = None,
    ) -> dict[str, Any]:
        """One page of Oil & Gas Field *source* records.

        Unlike :meth:`list_oil_gas_fields_page`, each item is a flat source view
        -- every business field plus ``id`` and ``source`` -- not an
        ``{"id": ..., "data": {...}}`` resource envelope. ``source_record`` is
        never included; use the per-id detail route for that.

        Only sources reachable through an ACTIVE membership on a live
        (non-merged) resource are listed, so absence from this result does not
        prove a source is absent from the database.

        Args:
            page: 1-based page number.
            page_size: rows per page, 1..``MAX_PAGE_SIZE``.
            source: restrict to these source keys; omit for every licensed
                source. Note a token holding only *some* ``source:read:<key>``
                permissions gets a 200 with the unlicensed rows silently
                dropped -- only a token holding *none* of them gets a 403.

        Raises:
            ValueError: if ``page``/``page_size`` are out of range, or ``source``
                is an empty sequence.
            StitchAPIError: on a non-2xx response (403 when the token holds no
                ``source:read:<key>`` permission at all).
        """
        self._validate_page_params(page, page_size)
        params: dict[str, Any] = {
            "page": page,
            "page_size": page_size,
            # Stable forward scan. The route defaults to name-ascending, under
            # which a concurrent insert can land behind the paging cursor and
            # shift every later page, silently skipping rows. Sorting on the
            # source id makes new rows append past the last page instead.
            "sort_by": "id",
            "sort_order": "asc",
        }
        if source is not None:
            source_keys = list(source)
            if not source_keys:
                # httpx drops an empty sequence from the query string entirely,
                # which the API reads as "no filter" -- i.e. every source, the
                # exact opposite of what the caller asked for.
                raise ValueError("source must not be empty when provided")
            params["source"] = source_keys
        payload = await self._request_json(
            method="GET",
            path="/oil-gas-field-sources/",
            operation="GET /oil-gas-field-sources/",
            params=params,
        )
        return self._expect_dict(payload, "GET /oil-gas-field-sources/")

    async def iter_oil_gas_field_sources(
        self,
        *,
        start_page: int = 1,
        page_size: int = 50,
        max_pages: int | None = None,
        source: Sequence[OGSISrcKey] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield Oil & Gas Field source records one page at a time.

        Bounded-memory full scan: only a single page is held in memory at once,
        so callers can fold the whole result set without materializing it. Page
        -termination logic mirrors :meth:`iter_oil_gas_fields`.
        """
        pages_fetched = 0
        page = start_page

        while True:
            if max_pages is not None and pages_fetched >= max_pages:
                return

            payload = await self.list_oil_gas_field_sources_page(
                page=page,
                page_size=page_size,
                source=source,
            )
            raw_item_count = self._item_count(payload)
            page_items = self._extract_items(payload)
            pages_fetched += 1

            if raw_item_count == 0:
                return

            for item in page_items:
                yield item

            total_pages = payload.get("total_pages")
            if isinstance(total_pages, int) and page >= total_pages:
                return

            if not isinstance(total_pages, int) and not page_items:
                return

            if raw_item_count < page_size:
                return

            page += 1

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

    async def list_merge_candidates(self) -> list[dict[str, Any]]:
        payload = await self._request_json(
            method="GET",
            path="/oil-gas-fields/merge-candidates",
            operation="GET /oil-gas-fields/merge-candidates",
        )
        return self._expect_list(payload, "GET /oil-gas-fields/merge-candidates")

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
    def _validate_page_params(page: int, page_size: int) -> None:
        """Reject out-of-range pagination locally rather than on a server 422.

        Applied by every paging entry point, so the ``iter_``/``collect_``
        wrappers inherit it through the page fetch they delegate to.
        """
        if page < 1:
            raise ValueError(f"page must be >= 1, got {page}")
        if not 1 <= page_size <= MAX_PAGE_SIZE:
            raise ValueError(
                f"page_size must be between 1 and {MAX_PAGE_SIZE}, got {page_size}"
            )

    @staticmethod
    def _expect_dict(payload: Any, operation: str) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        raise StitchAPIError(f"{operation} returned non-object JSON payload")

    @staticmethod
    def _expect_list(payload: Any, operation: str) -> list[dict[str, Any]]:
        if not isinstance(payload, list):
            raise StitchAPIError(f"{operation} returned non-array JSON payload")
        if not all(isinstance(item, dict) for item in payload):
            raise StitchAPIError(
                f"{operation} returned an array with non-object elements"
            )
        return payload

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
