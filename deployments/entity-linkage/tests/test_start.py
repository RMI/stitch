from __future__ import annotations

from contextlib import AbstractAsyncContextManager

import pytest
from fastapi import HTTPException

from stitch.entity_linkage.entities import (
    FieldCandidate,
    FieldDetailCandidate,
    MatchGroup,
    RequestAuthContext,
    User,
)
from stitch.entity_linkage.errors import StitchAPIError
from stitch.entity_linkage.routers import start as start_module
from stitch.entity_linkage.routers.start import (
    StartRequest,
    _extract_user_label,
    _group_duplicate_names,
    _normalize_country,
    _resolve_match_groups,
    start,
)


def make_auth_context(
    *,
    name: str = "Test User",
    email: str = "test@example.com",
    sub: str = "auth0|user-123",
    bearer_token: str | None = "token-123",
) -> RequestAuthContext:
    return RequestAuthContext(
        user=User(
            id=1,
            sub=sub,
            email=email,
            name=name,
        ),
        bearer_token=bearer_token,
    )


class FakeStitchApiClient(AbstractAsyncContextManager["FakeStitchApiClient"]):
    def __init__(
        self,
        auth_context: RequestAuthContext,
        *,
        items: list[FieldCandidate] | None = None,
        pages_fetched: int = 1,
        details_by_id: dict[int, FieldDetailCandidate] | None = None,
        merge_responses_by_ids: dict[tuple[int, ...], dict] | None = None,
        collect_error: Exception | None = None,
        detail_error: Exception | None = None,
        merge_error: Exception | None = None,
    ) -> None:
        self.auth_context = auth_context
        self.items = items or []
        self.pages_fetched = pages_fetched
        self.details_by_id = details_by_id or {}
        self.merge_responses_by_ids = merge_responses_by_ids or {}
        self.collect_error = collect_error
        self.detail_error = detail_error
        self.merge_error = merge_error

        self.collect_calls: list[dict] = []
        self.detail_calls: list[int] = []
        self.merge_calls: list[list[int]] = []

    async def __aenter__(self) -> "FakeStitchApiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def collect_oil_gas_fields(
        self,
        *,
        start_page: int = 1,
        page_size: int = 50,
        max_pages: int | None = None,
    ) -> tuple[list[FieldCandidate], int]:
        self.collect_calls.append(
            {
                "start_page": start_page,
                "page_size": page_size,
                "max_pages": max_pages,
            }
        )
        if self.collect_error is not None:
            raise self.collect_error
        return self.items, self.pages_fetched

    async def get_oil_gas_field_detail(self, resource_id: int) -> FieldDetailCandidate:
        self.detail_calls.append(resource_id)
        if self.detail_error is not None:
            raise self.detail_error
        return self.details_by_id[resource_id]

    async def create_merge_candidate(self, *, resource_ids: list[int]) -> dict:
        self.merge_calls.append(resource_ids)
        if self.merge_error is not None:
            raise self.merge_error
        return self.merge_responses_by_ids.get(tuple(resource_ids), {"ok": True})


@pytest.mark.parametrize(
    ("country", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("usa", "USA"),
        ("  usA  ", "USA"),
    ],
)
def test_normalize_country(country: str | None, expected: str | None) -> None:
    assert _normalize_country(country) == expected


def test_extract_user_label_prefers_name_then_email_then_sub() -> None:
    assert (
        _extract_user_label(
            User(id=1, sub="sub-1", email="a@example.com", name="Alice")
        )
        == "Alice"
    )
    assert (
        _extract_user_label(User(id=1, sub="sub-2", email="b@example.com", name=""))
        == "b@example.com"
    )
    assert (
        _extract_user_label(User(id=1, sub="sub-3", email="c@example.com", name=""))
        != "sub-3"
    )


def test_group_duplicate_names_uses_casefold_and_strips_whitespace() -> None:
    items = [
        FieldCandidate(id=1, name="Alpha", country="US"),
        FieldCandidate(id=2, name=" alpha ", country="CA"),
        FieldCandidate(id=3, name="BETA", country="US"),
        FieldCandidate(id=4, name="beta", country="MX"),
        FieldCandidate(id=5, name="Gamma", country="US"),
        FieldCandidate(id=6, name=None, country="US"),
        FieldCandidate(id=7, name="   ", country="US"),
    ]

    grouped = _group_duplicate_names(items)

    assert set(grouped.keys()) == {"alpha", "beta"}
    assert [item.id for item in grouped["alpha"]] == [1, 2]
    assert [item.id for item in grouped["beta"]] == [3, 4]


@pytest.mark.anyio
async def test_resolve_match_groups_groups_only_same_country_duplicates() -> None:
    duplicate_groups = {
        "alpha": [
            FieldCandidate(id=10, name="Alpha", country="ignored"),
            FieldCandidate(id=11, name="alpha", country="ignored"),
            FieldCandidate(id=12, name=" ALPHA ", country="ignored"),
        ],
        "beta": [
            FieldCandidate(id=20, name="Beta", country="ignored"),
            FieldCandidate(id=21, name="beta", country="ignored"),
        ],
    }

    client = FakeStitchApiClient(
        make_auth_context(),
        details_by_id={
            10: FieldDetailCandidate(id=10, name="Alpha", country=" us "),
            11: FieldDetailCandidate(id=11, name="Alpha", country="US"),
            12: FieldDetailCandidate(id=12, name="Alpha", country="CA"),
            20: FieldDetailCandidate(id=20, name="Beta", country=None),
            21: FieldDetailCandidate(id=21, name="Beta", country="MX"),
        },
    )

    match_groups, detail_records_fetched = await _resolve_match_groups(
        client=client,
        duplicate_groups=duplicate_groups,
    )

    assert detail_records_fetched == 5
    assert match_groups == [
        MatchGroup(ids=[10, 11], normalized_name="alpha", country="US"),
    ]
    assert client.detail_calls == [10, 11, 12, 20, 21]


@pytest.mark.anyio
async def test_start_returns_summary_without_merges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_context = make_auth_context(name="Alex Reviewer")
    fake_client = FakeStitchApiClient(
        auth_context,
        items=[
            FieldCandidate(id=1, name="Alpha", country="US"),
            FieldCandidate(id=2, name=" alpha ", country="CA"),
            FieldCandidate(id=3, name="Alpha", country="US"),
            FieldCandidate(id=4, name="Beta", country="NO"),
        ],
        pages_fetched=3,
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Alpha", country="US"),
            2: FieldDetailCandidate(id=2, name="Alpha", country="CA"),
            3: FieldDetailCandidate(id=3, name="Alpha", country=" us "),
        },
    )

    monkeypatch.setattr(
        start_module, "StitchApiClient", lambda auth_context: fake_client
    )

    response = await start(
        StartRequest(apply_merges=False, page=2, page_size=25, max_pages=4),
        auth_context=auth_context,
    )

    assert response.initiated_by == "Alex Reviewer"
    assert response.apply_merges is False
    assert response.relay_mode == "transparent"
    assert response.pages_fetched == 3
    assert response.total_records_fetched == 4
    assert response.duplicate_name_candidate_count == 3
    assert response.detail_records_fetched == 3
    assert response.match_groups == [[1, 3]]
    assert response.merge_results == []

    assert fake_client.collect_calls == [
        {"start_page": 2, "page_size": 25, "max_pages": 4}
    ]
    assert fake_client.merge_calls == []


@pytest.mark.anyio
async def test_start_applies_merges_for_each_match_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_context = make_auth_context()
    fake_client = FakeStitchApiClient(
        auth_context,
        items=[
            FieldCandidate(id=1, name="Alpha", country="ignored"),
            FieldCandidate(id=2, name="alpha", country="ignored"),
            FieldCandidate(id=3, name="Beta", country="ignored"),
            FieldCandidate(id=4, name="beta", country="ignored"),
        ],
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Alpha", country="US"),
            2: FieldDetailCandidate(id=2, name="Alpha", country="US"),
            3: FieldDetailCandidate(id=3, name="Beta", country="CA"),
            4: FieldDetailCandidate(id=4, name="Beta", country="CA"),
        },
        merge_responses_by_ids={
            (1, 2): {"merged_ids": [1, 2], "winner": 1},
            (3, 4): {"merged_ids": [3, 4], "winner": 3},
        },
    )

    monkeypatch.setattr(
        start_module, "StitchApiClient", lambda auth_context: fake_client
    )

    response = await start(
        StartRequest(apply_merges=True),
        auth_context=auth_context,
    )

    assert response.match_groups == [[1, 2], [3, 4]]
    assert fake_client.merge_calls == [[1, 2], [3, 4]]
    assert response.merge_results == [
        {"ids": [1, 2], "response": {"merged_ids": [1, 2], "winner": 1}},
        {"ids": [3, 4], "response": {"merged_ids": [3, 4], "winner": 3}},
    ]


@pytest.mark.anyio
async def test_start_returns_no_matches_when_duplicate_names_do_not_confirm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_context = make_auth_context()
    fake_client = FakeStitchApiClient(
        auth_context,
        items=[
            FieldCandidate(id=1, name="Alpha", country="ignored"),
            FieldCandidate(id=2, name="alpha", country="ignored"),
            FieldCandidate(id=3, name="Gamma", country="ignored"),
        ],
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Alpha", country="US"),
            2: FieldDetailCandidate(id=2, name="Alpha", country="CA"),
        },
    )

    monkeypatch.setattr(
        start_module, "StitchApiClient", lambda auth_context: fake_client
    )

    response = await start(
        StartRequest(apply_merges=True),
        auth_context=auth_context,
    )

    assert response.duplicate_name_candidate_count == 2
    assert response.detail_records_fetched == 2
    assert response.match_groups == []
    assert response.merge_results == []
    assert fake_client.merge_calls == []


@pytest.mark.anyio
async def test_start_translates_stitch_api_error_to_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_context = make_auth_context()
    fake_client = FakeStitchApiClient(
        auth_context,
        collect_error=StitchAPIError(
            "GET /oil-gas-fields/ failed with status 500: boom"
        ),
    )

    monkeypatch.setattr(
        start_module, "StitchApiClient", lambda auth_context: fake_client
    )

    with pytest.raises(HTTPException) as exc_info:
        await start(StartRequest(), auth_context=auth_context)

    exc = exc_info.value
    assert exc.status_code == 502
    assert exc.detail == "GET /oil-gas-fields/ failed with status 500: boom"
