from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError
from stitch.ogsi.model import OGFieldResource

from stitch.client import (
    AsyncStitchClient,
    STITCH_CLIENT_BEARER_TOKEN_ENV_VAR,
    StitchAPIError,
    env_bearer_token_headers_provider,
)


def make_client(
    handler,
    *,
    base_url: str = "http://example.test/api/v1",
    headers_provider=None,
) -> tuple[AsyncStitchClient, httpx.AsyncClient]:
    raw_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=base_url,
    )
    client = AsyncStitchClient(
        headers_provider=headers_provider,
        client=raw_client,
    )
    return client, raw_client


def make_valid_og_field_payload() -> dict[str, Any]:
    return {
        "id": None,
        "source_data": [
            {
                "id": None,
                "source": "gem",
                "name": "Alpha Field",
                "country": "USA",
                "source_record": {
                    "observed_at": "2026-01-01T00:00:00Z",
                    "producer": "test",
                    "payload": {"kind": "fixture"},
                },
            }
        ],
        "constituents": [],
    }


@pytest.mark.anyio
async def test_injected_client_allows_omitting_base_url() -> None:
    raw_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"items": [], "total_pages": 1})
        ),
        base_url="http://example.test/api/v1",
    )

    client = AsyncStitchClient(client=raw_client)

    payload = await client.list_oil_gas_fields_page()

    assert payload == {"items": [], "total_pages": 1}

    await raw_client.aclose()


@pytest.mark.anyio
async def test_aclose_does_not_close_injected_client() -> None:
    raw_client = httpx.AsyncClient(base_url="http://example.test/api/v1")
    client = AsyncStitchClient(client=raw_client)

    await client.aclose()

    assert raw_client.is_closed is False

    await raw_client.aclose()


@pytest.mark.anyio
async def test_aclose_closes_owned_client() -> None:
    client = AsyncStitchClient(base_url="http://example.test/api/v1")
    raw_client = client._client

    await client.aclose()

    assert raw_client.is_closed is True


def test_init_requires_base_url_without_injected_client() -> None:
    with pytest.raises(ValueError) as exc_info:
        AsyncStitchClient()

    assert str(exc_info.value) == "base_url is required when client is not provided"


@pytest.mark.anyio
async def test_init_rejects_base_url_when_client_is_injected() -> None:
    raw_client = httpx.AsyncClient(base_url="http://example.test/api/v1")

    with pytest.raises(ValueError) as exc_info:
        AsyncStitchClient(
            base_url="http://example.test/api/v1",
            client=raw_client,
        )

    assert (
        str(exc_info.value)
        == "base_url cannot be provided when client is already configured"
    )

    await raw_client.aclose()


@pytest.mark.anyio
async def test_init_rejects_timeout_when_client_is_injected() -> None:
    raw_client = httpx.AsyncClient(base_url="http://example.test/api/v1")

    with pytest.raises(ValueError) as exc_info:
        AsyncStitchClient(
            timeout=10.0,
            client=raw_client,
        )

    assert (
        str(exc_info.value)
        == "timeout cannot be provided when client is already configured"
    )

    await raw_client.aclose()


@pytest.mark.anyio
async def test_headers_provider_is_applied_to_each_request() -> None:
    calls = {"count": 0}
    captured: list[str | None] = []

    def headers_provider() -> dict[str, str]:
        calls["count"] += 1
        return {"X-Call": str(calls["count"])}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("X-Call"))
        return httpx.Response(200, json={"items": [], "total_pages": 1})

    client, raw_client = make_client(handler, headers_provider=headers_provider)

    await client.list_oil_gas_fields_page()
    await client.list_oil_gas_fields_page(page=2)

    assert captured == ["1", "2"]

    await raw_client.aclose()


@pytest.mark.anyio
async def test_env_bearer_token_mode_sends_token_on_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(STITCH_CLIENT_BEARER_TOKEN_ENV_VAR, "env-token-123")
    captured: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"items": [], "total_pages": 1})

    client, raw_client = make_client(
        handler,
        headers_provider=env_bearer_token_headers_provider(),
    )

    await client.list_oil_gas_fields_page()

    assert captured == ["Bearer env-token-123"]

    await raw_client.aclose()


def test_env_bearer_token_headers_provider_rejects_missing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(STITCH_CLIENT_BEARER_TOKEN_ENV_VAR, raising=False)
    provider = env_bearer_token_headers_provider()

    with pytest.raises(ValueError) as exc_info:
        provider()

    assert str(exc_info.value) == f"{STITCH_CLIENT_BEARER_TOKEN_ENV_VAR} must be set"


def test_env_bearer_token_headers_provider_rejects_blank_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(STITCH_CLIENT_BEARER_TOKEN_ENV_VAR, "   ")
    provider = env_bearer_token_headers_provider()

    with pytest.raises(ValueError) as exc_info:
        provider()

    assert str(exc_info.value) == f"{STITCH_CLIENT_BEARER_TOKEN_ENV_VAR} must be set"


@pytest.mark.anyio
async def test_wait_for_health_succeeds_after_retry() -> None:
    calls: list[int] = []
    observed_timeouts: list[dict[str, float]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(len(calls) + 1)
        observed_timeouts.append(request.extensions["timeout"])
        assert request.url.path == "/api/v1/health"
        if len(calls) == 1:
            return httpx.Response(503, text="warming up")
        return httpx.Response(200, json={"ok": True})

    client, raw_client = make_client(handler)

    await client.wait_for_health(retries=2, delay=0)

    assert calls == [1, 2]
    assert observed_timeouts == [
        {"connect": 2.0, "read": 2.0, "write": 2.0, "pool": 2.0},
        {"connect": 2.0, "read": 2.0, "write": 2.0, "pool": 2.0},
    ]

    await raw_client.aclose()


@pytest.mark.anyio
async def test_wait_for_health_raises_after_retries_are_exhausted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="still starting")

    client, raw_client = make_client(handler)

    with pytest.raises(RuntimeError) as exc_info:
        await client.wait_for_health(retries=2, delay=0)

    assert str(exc_info.value) == "GET /health did not become ready in time"

    await raw_client.aclose()


@pytest.mark.anyio
async def test_list_oil_gas_fields_page_sends_expected_request() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["query"] = request.url.query.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "items": [{"id": 1, "data": {"name": "Alpha", "country": "US"}}],
                "total_pages": 1,
            },
        )

    client, raw_client = make_client(handler)

    payload = await client.list_oil_gas_fields_page(page=3, page_size=25)

    assert payload["items"][0]["id"] == 1
    assert captured == {
        "method": "GET",
        "path": "/api/v1/oil-gas-fields/",
        "query": "page=3&page_size=25",
    }

    await raw_client.aclose()


@pytest.mark.anyio
async def test_list_oil_gas_fields_page_sends_filter_params() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json={"items": [], "total_pages": 1})

    client, raw_client = make_client(handler)

    await client.list_oil_gas_fields_page(
        page=1,
        page_size=50,
        q="Ghawar",
        name="Ghawar",
        country="Saudi Arabia",
    )

    assert captured["query"] == {
        "page": "1",
        "page_size": "50",
        "q": "Ghawar",
        "name": "Ghawar",
        "country": "Saudi Arabia",
    }

    await raw_client.aclose()


@pytest.mark.anyio
async def test_list_oil_gas_fields_page_omits_unset_filters() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = request.url.query.decode("utf-8")
        return httpx.Response(200, json={"items": [], "total_pages": 1})

    client, raw_client = make_client(handler)

    await client.list_oil_gas_fields_page(q="Ghawar")

    assert captured["query"] == "page=1&page_size=50&q=Ghawar"

    await raw_client.aclose()


@pytest.mark.anyio
async def test_iter_oil_gas_fields_streams_items_across_pages() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        calls.append(page)
        payloads = {
            1: {
                "items": [
                    {"id": 1, "data": {"name": "Alpha"}},
                    {"id": 2, "data": {"name": "Beta"}},
                ],
                "total_pages": 2,
            },
            2: {
                "items": [{"id": 3, "data": {"name": "Gamma"}}],
                "total_pages": 2,
            },
        }
        return httpx.Response(200, json=payloads[page])

    client, raw_client = make_client(handler)

    collected = [item["id"] async for item in client.iter_oil_gas_fields(page_size=2)]

    assert calls == [1, 2]
    assert collected == [1, 2, 3]

    await raw_client.aclose()


@pytest.mark.anyio
async def test_iter_oil_gas_fields_respects_max_pages_and_forwards_q() -> None:
    captured_q: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_q.append(request.url.params.get("q"))
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            json={
                "items": [{"id": page * 10 + 1}, {"id": page * 10 + 2}],
                "total_pages": 50,
            },
        )

    client, raw_client = make_client(handler)

    collected = [
        item["id"]
        async for item in client.iter_oil_gas_fields(
            start_page=1, page_size=2, max_pages=2, q="Alpha"
        )
    ]

    assert collected == [11, 12, 21, 22]
    assert captured_q == ["Alpha", "Alpha"]

    await raw_client.aclose()


@pytest.mark.anyio
async def test_list_merge_candidates_sends_expected_request() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(
            200,
            json=[{"id": 1, "resource_ids": [1, 2], "status": "PENDING"}],
        )

    client, raw_client = make_client(handler)

    candidates = await client.list_merge_candidates()

    assert candidates == [{"id": 1, "resource_ids": [1, 2], "status": "PENDING"}]
    assert captured == {
        "method": "GET",
        "path": "/api/v1/oil-gas-fields/merge-candidates",
    }

    await raw_client.aclose()


@pytest.mark.anyio
async def test_list_merge_candidates_rejects_non_array_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"not": "a-list"})

    client, raw_client = make_client(handler)

    with pytest.raises(StitchAPIError):
        await client.list_merge_candidates()

    await raw_client.aclose()


@pytest.mark.anyio
async def test_list_merge_candidates_rejects_non_object_elements() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"id": 1}, "not-a-dict"])

    client, raw_client = make_client(handler)

    with pytest.raises(StitchAPIError):
        await client.list_merge_candidates()

    await raw_client.aclose()


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

    client, raw_client = make_client(handler)

    items, pages_fetched = await client.collect_oil_gas_fields(
        start_page=1,
        page_size=2,
    )

    assert pages_fetched == 2
    assert [item["id"] for item in items] == [1, 2, 3]

    await raw_client.aclose()


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

    client, raw_client = make_client(handler)

    items, pages_fetched = await client.collect_oil_gas_fields(
        start_page=5,
        page_size=2,
    )

    assert calls == [5, 6]
    assert pages_fetched == 2
    assert [item["id"] for item in items] == [10, 11, 12]

    await raw_client.aclose()


@pytest.mark.anyio
async def test_collect_oil_gas_fields_treats_non_list_items_as_empty() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(int(request.url.params["page"]))
        return httpx.Response(200, json={"items": {"not": "a-list"}})

    client, raw_client = make_client(handler)

    items, pages_fetched = await client.collect_oil_gas_fields()

    assert calls == [1]
    assert items == []
    assert pages_fetched == 1

    await raw_client.aclose()


@pytest.mark.anyio
async def test_collect_oil_gas_fields_does_not_stop_on_filtered_full_page() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        calls.append(page)
        payloads = {
            1: {
                "items": [
                    {"id": 1, "data": {"name": "Alpha", "country": "US"}},
                    "not-a-dict",
                ],
                "total_pages": 2,
            },
            2: {
                "items": [
                    {"id": 2, "data": {"name": "Beta", "country": "CA"}},
                ],
                "total_pages": 2,
            },
        }
        return httpx.Response(200, json=payloads[page])

    client, raw_client = make_client(handler)

    items, pages_fetched = await client.collect_oil_gas_fields(page_size=2)

    assert calls == [1, 2]
    assert pages_fetched == 2
    assert [item["id"] for item in items] == [1, 2]

    await raw_client.aclose()


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
                    {"id": page * 100 + 1},
                    {"id": page * 100 + 2},
                ],
                "total_pages": 50,
            },
        )

    client, raw_client = make_client(handler)

    items, pages_fetched = await client.collect_oil_gas_fields(
        start_page=2,
        page_size=2,
        max_pages=2,
    )

    assert calls == [2, 3]
    assert pages_fetched == 2
    assert [item["id"] for item in items] == [201, 202, 301, 302]

    await raw_client.aclose()


@pytest.mark.anyio
async def test_create_oil_gas_field_sends_expected_request() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"id": 7})

    client, raw_client = make_client(handler)

    validated_payload = make_valid_og_field_payload()
    payload = await client.create_oil_gas_field(validated_payload)

    assert payload == {"id": 7}
    assert captured == {
        "method": "POST",
        "path": "/api/v1/oil-gas-fields/",
        "body": validated_payload,
    }

    await raw_client.aclose()


@pytest.mark.anyio
async def test_create_oil_gas_field_accepts_typed_model() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"id": 7})

    client, raw_client = make_client(handler)
    model_payload = OGFieldResource.model_validate(make_valid_og_field_payload())

    await client.create_oil_gas_field(model_payload)

    assert captured["body"] == make_valid_og_field_payload()

    await raw_client.aclose()


@pytest.mark.anyio
async def test_create_oil_gas_field_rejects_invalid_mapping_before_request() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"id": 7})

    client, raw_client = make_client(handler)

    with pytest.raises(ValidationError):
        await client.create_oil_gas_field(
            {
                "id": None,
                "source_data": [
                    {
                        "source": "gem",
                        "country": "USA",
                    }
                ],
            }
        )

    assert called is False

    await raw_client.aclose()


@pytest.mark.anyio
async def test_create_merge_candidate_sends_expected_request() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"merged": True})

    client, raw_client = make_client(handler)

    payload = await client.create_merge_candidate([7, 8])

    assert payload == {"merged": True}
    assert captured == {
        "method": "POST",
        "path": "/api/v1/oil-gas-fields/merge-candidates",
        "body": {"resource_ids": [7, 8]},
    }

    await raw_client.aclose()


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
        AsyncStitchClient._raise_for_status(response, operation)

    assert (
        str(exc_info.value) == f"{operation} failed with status {status_code}: {text}"
    )
    assert exc_info.value.status_code == status_code
    assert exc_info.value.response_text == text
