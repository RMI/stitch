from __future__ import annotations

from contextlib import AbstractAsyncContextManager

import pytest

from stitch.entity_linkage import matching
from stitch.entity_linkage.entities import FieldCandidate, FieldDetailCandidate
from stitch.entity_linkage.errors import StitchAPIError


class FakeMatchingClient(AbstractAsyncContextManager["FakeMatchingClient"]):
    """In-memory stand-in for StitchApiClient.

    ``collect_oil_gas_fields`` simulates the API's case-insensitive ``q`` (ILIKE)
    filter over the name, so the matcher's superset+refilter can be exercised.
    """

    def __init__(
        self,
        *,
        items: list[FieldCandidate] | None = None,
        details_by_id: dict[int, FieldDetailCandidate] | None = None,
        existing_candidates: list[dict] | None = None,
        create_error: Exception | None = None,
    ) -> None:
        self.items = items or []
        self.details_by_id = details_by_id or {}
        self.existing_candidates = existing_candidates or []
        self.create_error = create_error

        self.detail_calls: list[int] = []
        self.collect_q: list[str | None] = []
        self.create_calls: list[list[int]] = []
        self.list_candidates_calls = 0

    async def __aenter__(self) -> "FakeMatchingClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get_oil_gas_field_detail(self, resource_id: int) -> FieldDetailCandidate:
        self.detail_calls.append(resource_id)
        return self.details_by_id[resource_id]

    async def collect_oil_gas_fields(
        self,
        *,
        start_page: int = 1,
        page_size: int = 50,
        max_pages: int | None = None,
        q: str | None = None,
        name: str | None = None,
        country: str | None = None,
    ) -> tuple[list[FieldCandidate], int]:
        self.collect_q.append(q)
        superset = [
            item
            for item in self.items
            if q is None
            or (item.name is not None and q.casefold() in item.name.casefold())
        ]
        return superset, 1

    async def iter_oil_gas_fields(
        self,
        *,
        start_page: int = 1,
        page_size: int = 50,
        max_pages: int | None = None,
        q: str | None = None,
        name: str | None = None,
        country: str | None = None,
    ):
        for item in self.items:
            yield item

    async def create_merge_candidate(self, *, resource_ids: list[int]) -> dict:
        self.create_calls.append(list(resource_ids))
        if self.create_error is not None:
            raise self.create_error
        return {"ok": True, "resource_ids": list(resource_ids)}

    async def list_merge_candidates(self) -> list[dict]:
        self.list_candidates_calls += 1
        return self.existing_candidates


def test_merge_fingerprint_is_sorted_and_deduped() -> None:
    assert matching.merge_fingerprint([3, 1, 2, 1]) == "1:2:3"
    assert matching.merge_fingerprint([2, 1]) == matching.merge_fingerprint([1, 2])


@pytest.mark.anyio
async def test_find_match_group_blocks_by_casefold_name_and_country() -> None:
    # id=4 shares the "ghawar" substring (so the API superset returns it) but its
    # normalized name differs; the exact API name filter would have missed the
    # case/whitespace variants (2, 3) that this superset+refilter keeps.
    client = FakeMatchingClient(
        items=[
            FieldCandidate(id=1, name="Ghawar", country="Saudi Arabia"),
            FieldCandidate(id=2, name=" ghawar ", country="saudi arabia"),
            FieldCandidate(id=3, name="GHAWAR", country="Kuwait"),
            FieldCandidate(id=4, name="Ghawar North", country="Saudi Arabia"),
        ],
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Ghawar", country="Saudi Arabia"),
            2: FieldDetailCandidate(id=2, name=" ghawar ", country="saudi arabia"),
            3: FieldDetailCandidate(id=3, name="GHAWAR", country="Kuwait"),
        },
    )

    matched = await matching.find_match_group_for_resource(client, 1)

    assert matched == [1, 2]
    assert client.collect_q == ["Ghawar"]
    # Seed detail is fetched once up front and reused (not re-fetched in the loop).
    assert client.detail_calls == [1, 2, 3]


@pytest.mark.anyio
async def test_find_match_group_returns_empty_without_country() -> None:
    client = FakeMatchingClient(
        items=[
            FieldCandidate(id=1, name="Alpha", country=None),
            FieldCandidate(id=2, name="alpha", country="US"),
        ],
        details_by_id={1: FieldDetailCandidate(id=1, name="Alpha", country=None)},
    )

    matched = await matching.find_match_group_for_resource(client, 1)

    assert matched == []


@pytest.mark.anyio
async def test_find_match_group_returns_empty_for_unique_name() -> None:
    client = FakeMatchingClient(
        items=[
            FieldCandidate(id=1, name="Solo", country="US"),
            FieldCandidate(id=2, name="Other", country="US"),
        ],
        details_by_id={1: FieldDetailCandidate(id=1, name="Solo", country="US")},
    )

    matched = await matching.find_match_group_for_resource(client, 1)

    assert matched == []


@pytest.mark.anyio
async def test_link_resource_dry_run_does_not_submit() -> None:
    client = FakeMatchingClient(
        items=[
            FieldCandidate(id=1, name="Alpha", country="US"),
            FieldCandidate(id=2, name="alpha", country="US"),
        ],
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Alpha", country="US"),
            2: FieldDetailCandidate(id=2, name="alpha", country="US"),
        },
    )

    result = await matching.link_resource(client, 1, apply_merges=False)

    assert result.matched_ids == [1, 2]
    assert result.merge_candidate_created is False
    assert result.skipped_existing is False
    assert client.create_calls == []


@pytest.mark.anyio
async def test_link_resource_applies_merge() -> None:
    client = FakeMatchingClient(
        items=[
            FieldCandidate(id=1, name="Alpha", country="US"),
            FieldCandidate(id=2, name="alpha", country="US"),
        ],
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Alpha", country="US"),
            2: FieldDetailCandidate(id=2, name="alpha", country="US"),
        },
    )

    result = await matching.link_resource(client, 1, apply_merges=True)

    assert result.merge_candidate_created is True
    assert result.skipped_existing is False
    assert client.create_calls == [[1, 2]]


@pytest.mark.anyio
async def test_link_resource_skips_when_candidate_already_exists() -> None:
    client = FakeMatchingClient(
        items=[
            FieldCandidate(id=1, name="Alpha", country="US"),
            FieldCandidate(id=2, name="alpha", country="US"),
        ],
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Alpha", country="US"),
            2: FieldDetailCandidate(id=2, name="alpha", country="US"),
        },
        create_error=StitchAPIError(
            "POST /oil-gas-fields/merge-candidates failed with status 400: exists",
            status_code=400,
        ),
    )

    result = await matching.link_resource(client, 1, apply_merges=True)

    assert result.merge_candidate_created is False
    assert result.skipped_existing is True
    assert client.create_calls == [[1, 2]]


@pytest.mark.anyio
async def test_link_resource_skips_known_existing_without_posting() -> None:
    client = FakeMatchingClient(
        items=[
            FieldCandidate(id=1, name="Alpha", country="US"),
            FieldCandidate(id=2, name="alpha", country="US"),
        ],
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Alpha", country="US"),
            2: FieldDetailCandidate(id=2, name="alpha", country="US"),
        },
    )

    result = await matching.link_resource(
        client, 1, apply_merges=True, known_existing={"1:2"}
    )

    assert result.skipped_existing is True
    assert result.merge_candidate_created is False
    assert client.create_calls == []


@pytest.mark.anyio
async def test_link_resource_propagates_non_4xx_downstream_error() -> None:
    client = FakeMatchingClient(
        items=[
            FieldCandidate(id=1, name="Alpha", country="US"),
            FieldCandidate(id=2, name="alpha", country="US"),
        ],
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Alpha", country="US"),
            2: FieldDetailCandidate(id=2, name="alpha", country="US"),
        },
        create_error=StitchAPIError("boom", status_code=500),
    )

    with pytest.raises(StitchAPIError):
        await matching.link_resource(client, 1, apply_merges=True)


@pytest.mark.anyio
async def test_link_all_dedupes_groups_and_submits_once() -> None:
    # Two same-name+country blocks plus a singleton; every member rediscovers its
    # block, but each block is submitted at most once.
    client = FakeMatchingClient(
        items=[
            FieldCandidate(id=1, name="Alpha", country="US"),
            FieldCandidate(id=2, name="alpha", country="US"),
            FieldCandidate(id=3, name="Alpha", country="CA"),
            FieldCandidate(id=4, name="alpha", country="CA"),
            FieldCandidate(id=5, name="Beta", country="US"),
        ],
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Alpha", country="US"),
            2: FieldDetailCandidate(id=2, name="alpha", country="US"),
            3: FieldDetailCandidate(id=3, name="Alpha", country="CA"),
            4: FieldDetailCandidate(id=4, name="alpha", country="CA"),
            5: FieldDetailCandidate(id=5, name="Beta", country="US"),
        },
    )

    response = await matching.link_all(
        client, apply_merges=True, page_size=200, initiated_by="Tester"
    )

    assert response.resources_scanned == 5
    assert response.match_groups == [[1, 2], [3, 4]]
    assert response.merge_candidates_created == 2
    assert response.merge_candidates_skipped == 0
    # {1,2} found at seed 1, {3,4} at seed 3; members 2 and 4 are skipped as
    # already-processed, so only two POSTs happen.
    assert client.create_calls == [[1, 2], [3, 4]]


@pytest.mark.anyio
async def test_link_all_skips_groups_already_in_the_queue() -> None:
    client = FakeMatchingClient(
        items=[
            FieldCandidate(id=1, name="Alpha", country="US"),
            FieldCandidate(id=2, name="alpha", country="US"),
        ],
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Alpha", country="US"),
            2: FieldDetailCandidate(id=2, name="alpha", country="US"),
        },
        existing_candidates=[{"id": 99, "resource_ids": [1, 2], "status": "PENDING"}],
    )

    response = await matching.link_all(
        client, apply_merges=True, page_size=200, initiated_by="Tester"
    )

    assert response.match_groups == [[1, 2]]
    assert response.merge_candidates_created == 0
    assert response.merge_candidates_skipped == 1
    assert client.create_calls == []
    assert client.list_candidates_calls == 1
