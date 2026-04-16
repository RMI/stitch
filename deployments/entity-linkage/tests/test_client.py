from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from stitch.entity_linkage.client import StitchApiClient
from stitch.entity_linkage.entities import RequestAuthContext, User
from stitch.entity_linkage.errors import StitchAPIError


def make_auth_context(
    *,
    bearer_token: str | None = "token-123",
) -> RequestAuthContext:
    return RequestAuthContext(
        user=User(
            id=1,
            sub="auth0|user-123",
            email="test@example.com",
            name="Test User",
        ),
        bearer_token=bearer_token,
    )


def make_client(
    handler,
    *,
    bearer_token: str | None = "token-123",
    base_url: str = "http://example.test/api/v1",
) -> StitchApiClient:
    client = StitchApiClient(auth_context=make_auth_context(bearer_token=bearer_token))
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=base_url,
    )
    return client


@pytest.mark.anyio
async def test_headers_include_bearer_token_when_present() -> None:
    client = make_client(lambda request: httpx.Response(200, json={"items": []}))

    assert client._headers() == {"Authorization": "Bearer token-123"}

    await client.aclose()


@pytest.mark.anyio
async def test_headers_are_empty_without_bearer_token() -> None:
    client = make_client(
        lambda request: httpx.Response(200, json={"items": []}),
        bearer_token=None,
    )

    assert client._headers() == {}

    await client.aclose()


@pytest.mark.anyio
async def test_list_oil_gas_fields_page_sends_expected_request() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["query"] = request.url.query.decode("utf-8")
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "items": [{"id": 1, "data": {"name": "Alpha", "country": "US"}}],
                "total_pages": 1,
            },
        )

    client = make_client(handler)

    payload = await client.list_oil_gas_fields_page(page=3, page_size=25)

    assert payload["items"][0]["id"] == 1
    assert captured == {
        "method": "GET",
        "path": "/api/v1/oil-gas-fields/",
        "query": "page=3&page_size=25",
        "authorization": "Bearer token-123",
    }

    await client.aclose()


@pytest.mark.anyio
async def test_collect_oil_gas_fields_follows_total_pages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        payloads = {
            1: {
                "items": [
                    {"id": 1, "data": {"name": "Alpha", "country": "US"}},
                    {"id": 2, "data": {"name": "Beta", "country": "CA"}},
                ],
                "total_pages": 2,
            },
            2: {
                "items": [
                    {"id": 3, "data": {"name": "Gamma", "country": "MX"}},
                ],
                "total_pages": 2,
            },
        }
        return httpx.Response(200, json=payloads[page])

    client = make_client(handler)

    items, pages_fetched = await client.collect_oil_gas_fields(
        start_page=1, page_size=2
    )

    assert pages_fetched == 2
    assert [item.id for item in items] == [1, 2, 3]
    assert [item.normalized_name for item in items] == ["alpha", "beta", "gamma"]

    await client.aclose()


@pytest.mark.anyio
async def test_collect_oil_gas_fields_stops_when_page_is_short() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        calls.append(page)
        payloads = {
            5: {
                "items": [
                    {"id": 10, "data": {"name": "Alpha", "country": "US"}},
                    {"id": 11, "data": {"name": "Beta", "country": "CA"}},
                ],
            },
            6: {
                "items": [
                    {"id": 12, "data": {"name": "Gamma", "country": "MX"}},
                ],
            },
        }
        return httpx.Response(200, json=payloads[page])

    client = make_client(handler)

    items, pages_fetched = await client.collect_oil_gas_fields(
        start_page=5, page_size=2
    )

    assert calls == [5, 6]
    assert pages_fetched == 2
    assert [item.id for item in items] == [10, 11, 12]

    await client.aclose()


@pytest.mark.anyio
async def test_collect_oil_gas_fields_respects_max_pages() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        calls.append(page)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": page * 100 + 1,
                        "data": {"name": f"Name {page}", "country": "US"},
                    },
                    {
                        "id": page * 100 + 2,
                        "data": {"name": f"Other {page}", "country": "US"},
                    },
                ],
                "total_pages": 50,
            },
        )

    client = make_client(handler)

    items, pages_fetched = await client.collect_oil_gas_fields(
        start_page=2,
        page_size=2,
        max_pages=2,
    )

    assert calls == [2, 3]
    assert pages_fetched == 2
    assert [item.id for item in items] == [201, 202, 301, 302]

    await client.aclose()


@pytest.mark.anyio
async def test_collect_oil_gas_fields_treats_non_list_items_as_empty() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(int(request.url.params["page"]))
        return httpx.Response(200, json={"items": {"not": "a-list"}})

    client = make_client(handler)

    items, pages_fetched = await client.collect_oil_gas_fields()

    assert calls == [1]
    assert items == []
    assert pages_fetched == 1

    await client.aclose()


@pytest.mark.anyio
async def test_to_candidates_handles_missing_data_block() -> None:
    items = [
        {"id": 1, "data": {"name": "Alpha", "country": "US"}},
        {"id": 2, "data": None},
        {"id": 3},
    ]

    candidates = StitchApiClient._to_candidates(items)

    assert [
        (candidate.id, candidate.name, candidate.country) for candidate in candidates
    ] == [
        (1, "Alpha", "US"),
        (2, None, None),
        (3, None, None),
    ]


@pytest.mark.anyio
async def test_get_oil_gas_field_detail_maps_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/oil-gas-fields/42/detail"
        assert request.headers["Authorization"] == "Bearer token-123"
        return httpx.Response(
            200,
            json={"id": 42, "data": {"name": "Alpha", "country": "US"}},
        )

    client = make_client(handler)

    detail = await client.get_oil_gas_field_detail(42)

    assert detail.id == 42
    assert detail.name == "Alpha"
    assert detail.country == "US"

    await client.aclose()


@pytest.mark.anyio
async def test_post_merge_sends_current_branch_payload_shape() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"merged": True})

    client = make_client(handler)

    payload = await client.create_merge_candidate(resource_ids=[7, 8])

    assert payload == {"merged": True}
    assert captured == {
        "method": "POST",
        "path": "/api/v1/oil-gas-fields/merge-candidates",
        "authorization": "Bearer token-123",
        "body": {"resource_ids": [7, 8]},
    }

    await client.aclose()


@pytest.mark.parametrize(
    ("status_code", "text", "operation"),
    [
        (500, "server exploded", "GET /oil-gas-fields/"),
        (404, "missing", "GET /oil-gas-fields/123/detail"),
        (400, "bad request", "POST /oil-gas-fields/merge"),
    ],
)
def test_raise_for_status_raises_stitch_api_error(
    status_code: int,
    text: str,
    operation: str,
) -> None:
    response = httpx.Response(status_code, text=text)

    with pytest.raises(StitchAPIError) as exc_info:
        StitchApiClient._raise_for_status(response, operation)

    assert (
        str(exc_info.value) == f"{operation} failed with status {status_code}: {text}"
    )
