from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from stitch.api.entities import (
    MergeCandidateCreateRequest,
    MergeCandidateDetailView,
    MergeCandidateQueryParams,
    MergeCandidateReviewRequest,
    MergeCandidateStatus,
)
from stitch.api.db.errors import InvalidActionError, ResourceNotFoundError
from stitch.api.db import merge_candidate_actions as mca
from stitch.ogsi.model.og_field import OilGasFieldBase

from datetime import datetime, timezone

NOW = datetime.now(timezone.utc)


@dataclass
class FakeItem:
    resource_id: int
    position: int


@dataclass
class FakeCandidate:
    id: int
    status: MergeCandidateStatus
    items: list[FakeItem]
    fingerprint: str = ""
    review_notes: str | None = None
    merged_resource_id: int | None = None
    created: object = NOW
    updated: object = NOW
    created_by_id: int = 1
    last_updated_by_id: int = 1
    reviewed_at: object | None = None
    reviewed_by_id: int | None = None


@dataclass
class FakeMergedResource:
    id: int


@dataclass
class FakeSession:
    scalar_result: object | None = None
    scalars_result: list[object] = field(default_factory=list)
    execute_rows: list[tuple] = field(default_factory=list)
    added: list[object] = field(default_factory=list)
    added_all: list[object] = field(default_factory=list)
    deleted: list[object] = field(default_factory=list)
    flush_calls: int = 0
    refresh_calls: list[tuple[object, object | None]] = field(default_factory=list)

    async def scalar(self, _stmt):
        return self.scalar_result

    async def scalars(self, _stmt):
        return SimpleNamespace(all=lambda: list(self.scalars_result))

    async def execute(self, _stmt):
        return SimpleNamespace(all=lambda: list(self.execute_rows))

    def add(self, obj):
        self.added.append(obj)

    def add_all(self, objs):
        self.added_all.extend(list(objs))

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        self.flush_calls += 1

    async def refresh(self, obj, attrs=None):
        self.refresh_calls.append((obj, attrs))


@pytest.fixture
def user():
    return SimpleNamespace(id=123)


def test_normalize_resource_ids_dedupes_preserving_order():
    assert mca._normalize_resource_ids([18, 19, 18, 20]) == [18, 19, 20]
    assert mca._normalize_resource_ids([20, 18, 19, 20]) == [20, 18, 19]


def test_normalize_resource_ids_requires_at_least_two_unique_ids():
    with pytest.raises(InvalidActionError, match="multiple ids"):
        mca._normalize_resource_ids([18, 18])


def test_fingerprint_is_order_insensitive_and_deduped():
    assert mca._fingerprint([19, 18, 19]) == "18:19"


def test_candidate_to_view_sorts_items_by_position():
    candidate = FakeCandidate(
        id=1,
        status=MergeCandidateStatus.PENDING,
        items=[
            FakeItem(resource_id=19, position=1),
            FakeItem(resource_id=18, position=0),
        ],
    )

    view = mca._candidate_to_view(candidate)

    assert view.resource_ids == [18, 19]
    assert view.status == MergeCandidateStatus.PENDING
    assert view.id == 1


def _named(name: str | None, source: str = "rmi", source_pk: int = 1):
    """A coalesced resource whose only known field is ``name``."""
    return SimpleNamespace(
        view=OilGasFieldBase(name=name, country=None),
        provenance={"name": None if name is None else (name, source, source_pk)},
    )


@pytest.mark.anyio
async def test_list_merge_candidates_returns_page_with_names_and_counts(
    monkeypatch,
):
    first = FakeCandidate(
        id=2,
        status=MergeCandidateStatus.PENDING,
        items=[FakeItem(18, 0), FakeItem(19, 1)],
    )
    second = FakeCandidate(
        id=1,
        status=MergeCandidateStatus.APPROVED,
        items=[FakeItem(20, 0), FakeItem(21, 1)],
        merged_resource_id=30,
    )
    session = FakeSession(
        scalar_result=7,
        scalars_result=[first, second],
        execute_rows=[("PENDING", 5), ("APPROVED", 2)],
    )

    async def fake_coalesce(session_arg, resource_ids, licensed):
        assert resource_ids == [18, 19, 20, 21, 30]
        assert licensed == ["rmi"]
        return {
            18: _named("From WM", source="wm"),
            19: _named("From RMI", source="rmi"),
            # Merged-away originals are null shells; the merged resource names it.
            20: _named(None),
            21: _named(None),
            30: _named("Merged"),
        }

    monkeypatch.setattr(mca, "coalesce_resources", fake_coalesce)

    page = await mca.list_merge_candidates(
        session, MergeCandidateQueryParams(page=1, page_size=2), ["rmi"]
    )

    assert [view.id for view in page.items] == [2, 1]
    assert page.items[0].resource_ids == [18, 19]
    # Best-ranked source wins regardless of resource order.
    assert page.items[0].name == "From RMI"
    assert page.items[1].name == "Merged"
    assert page.total_count == 7
    assert page.total_pages == 4
    # Every status is reported, including ones with no candidates.
    assert page.status_counts == {
        MergeCandidateStatus.PENDING: 5,
        MergeCandidateStatus.APPROVED: 2,
        MergeCandidateStatus.DENIED: 0,
    }


def test_candidate_name_breaks_rank_ties_by_resource_position():
    candidate = FakeCandidate(
        id=1,
        status=MergeCandidateStatus.PENDING,
        items=[FakeItem(19, 1), FakeItem(18, 0)],
    )
    coalesced = {18: _named("First"), 19: _named("Second")}

    assert mca._candidate_name(candidate, coalesced) == "First"


def test_candidate_name_is_none_without_a_licensed_name():
    candidate = FakeCandidate(
        id=1,
        status=MergeCandidateStatus.PENDING,
        items=[FakeItem(18, 0), FakeItem(19, 1)],
    )
    coalesced = {18: _named(None), 19: _named(None)}

    assert mca._candidate_name(candidate, coalesced) is None


@pytest.mark.anyio
async def test_get_merge_candidate_raises_when_missing():
    session = FakeSession(scalar_result=None)

    with pytest.raises(ResourceNotFoundError, match="No merge candidate found"):
        await mca.get_merge_candidate(session, candidate_id=999)


@pytest.mark.anyio
async def test_create_merge_candidate_rejects_existing_pending(monkeypatch, user):
    existing = FakeCandidate(
        id=1,
        status=MergeCandidateStatus.PENDING,
        items=[FakeItem(18, 0), FakeItem(19, 1)],
    )
    session = FakeSession(scalar_result=existing)
    monkeypatch.setattr(mca, "_load_mergeable_resources", AsyncMock())

    with pytest.raises(
        InvalidActionError, match="pending merge candidate already exists"
    ):
        await mca.create_merge_candidate(
            session=session,
            user=user,
            request=MergeCandidateCreateRequest(resource_ids=[18, 19]),
        )


@pytest.mark.anyio
async def test_create_merge_candidate_rejects_existing_denied(monkeypatch, user):
    existing = FakeCandidate(
        id=1,
        status=MergeCandidateStatus.DENIED,
        items=[FakeItem(18, 0), FakeItem(19, 1)],
    )
    session = FakeSession(scalar_result=existing)
    monkeypatch.setattr(mca, "_load_mergeable_resources", AsyncMock())

    with pytest.raises(
        InvalidActionError, match="denied merge candidate already exists"
    ):
        await mca.create_merge_candidate(
            session=session,
            user=user,
            request=MergeCandidateCreateRequest(resource_ids=[18, 19]),
        )


@pytest.mark.anyio
async def test_create_merge_candidate_rejects_existing_approved(monkeypatch, user):
    existing = FakeCandidate(
        id=1,
        status=MergeCandidateStatus.APPROVED,
        items=[FakeItem(18, 0), FakeItem(19, 1)],
    )
    session = FakeSession(scalar_result=existing)
    monkeypatch.setattr(mca, "_load_mergeable_resources", AsyncMock())

    with pytest.raises(
        InvalidActionError, match="approved merge candidate already exists"
    ):
        await mca.create_merge_candidate(
            session=session,
            user=user,
            request=MergeCandidateCreateRequest(resource_ids=[18, 19]),
        )


@pytest.mark.anyio
async def test_create_merge_candidate_persists_candidate_and_items(monkeypatch, user):
    created = FakeCandidate(
        id=42, status=MergeCandidateStatus.PENDING, items=[], fingerprint="18:19"
    )
    session = FakeSession(scalar_result=None)

    monkeypatch.setattr(mca, "_load_mergeable_resources", AsyncMock())
    monkeypatch.setattr(
        mca.MergeCandidateModel,
        "create",
        staticmethod(lambda created_by, fingerprint: created),
    )

    @dataclass
    class FakeItemModel:
        merge_candidate_id: int
        resource_id: int
        position: int

    monkeypatch.setattr(mca, "MergeCandidateItemModel", FakeItemModel)

    async def fake_refresh(candidate, attrs=None):
        candidate.items = [
            FakeItem(resource_id=18, position=0),
            FakeItem(resource_id=19, position=1),
        ]
        session.refresh_calls.append((candidate, attrs))

    session.refresh = fake_refresh

    view = await mca.create_merge_candidate(
        session=session,
        user=user,
        request=MergeCandidateCreateRequest(resource_ids=[18, 19]),
    )

    assert session.added == [created]
    assert [(item.resource_id, item.position) for item in session.added_all] == [
        (18, 0),
        (19, 1),
    ]
    assert session.flush_calls == 2
    assert view.id == 42
    assert view.resource_ids == [18, 19]
    assert view.status == MergeCandidateStatus.PENDING


@pytest.mark.anyio
async def test_approve_merge_candidate_rejects_non_pending(user):
    candidate = FakeCandidate(
        id=7,
        status=MergeCandidateStatus.APPROVED,
        items=[FakeItem(18, 0), FakeItem(19, 1)],
    )
    session = FakeSession(scalar_result=candidate)

    with pytest.raises(InvalidActionError, match="is not pending"):
        await mca.approve_merge_candidate(session=session, user=user, candidate_id=7)


@pytest.mark.anyio
async def test_approve_merge_candidate_applies_merge_and_updates_candidate(
    monkeypatch, user
):
    candidate = FakeCandidate(
        id=7,
        status=MergeCandidateStatus.PENDING,
        items=[FakeItem(18, 0), FakeItem(19, 1)],
    )
    session = FakeSession(scalar_result=candidate)
    load_mergeable = AsyncMock()
    apply_merge = AsyncMock(return_value=FakeMergedResource(id=31))
    monkeypatch.setattr(mca, "_load_mergeable_resources", load_mergeable)
    monkeypatch.setattr(mca, "apply_resource_merge", apply_merge)

    view = await mca.approve_merge_candidate(
        session=session,
        user=user,
        candidate_id=7,
        request=MergeCandidateReviewRequest(review_notes="looks good"),
    )

    load_mergeable.assert_awaited_once_with(session, [18, 19])
    apply_merge.assert_awaited_once_with(
        session=session, user=user, resource_ids=[18, 19]
    )
    assert candidate.status == MergeCandidateStatus.APPROVED
    assert candidate.review_notes == "looks good"
    assert candidate.reviewed_by_id == user.id
    assert candidate.last_updated_by_id == user.id
    assert candidate.merged_resource_id == 31
    assert session.flush_calls == 1
    assert view.status == MergeCandidateStatus.APPROVED
    assert view.merged_resource_id == 31


@pytest.mark.anyio
async def test_reroute_rewrites_pending_candidate_items_and_fingerprint(user):
    # Approving A(18)+B(19) -> D(31) must repoint pending A(18)+C(20) to D+C.
    other = FakeCandidate(
        id=5,
        status=MergeCandidateStatus.PENDING,
        items=[FakeItem(18, 0), FakeItem(20, 1)],
        fingerprint="18:20",
    )
    session = FakeSession(scalars_result=[other])

    await mca._reroute_pending_candidates(
        session=session,
        user=user,
        merged_away_ids=[18, 19],
        new_id=31,
    )

    assert [(i.resource_id, i.position) for i in other.items] == [(31, 0), (20, 1)]
    assert other.fingerprint == "20:31"
    assert other.last_updated_by_id == user.id
    assert session.deleted == []


@pytest.mark.anyio
async def test_reroute_dedupes_when_candidate_holds_multiple_merged_ids(user):
    # A 3-way A(18)+B(19)+C(20): approving A+B -> D(31) collapses both A and B to
    # D, so the duplicate item is dropped and the candidate becomes D+C.
    other = FakeCandidate(
        id=5,
        status=MergeCandidateStatus.PENDING,
        items=[FakeItem(18, 0), FakeItem(19, 1), FakeItem(20, 2)],
        fingerprint="18:19:20",
    )
    session = FakeSession(scalars_result=[other])

    await mca._reroute_pending_candidates(
        session=session,
        user=user,
        merged_away_ids=[18, 19],
        new_id=31,
    )

    # The second merged-away member (position 1) is the dropped duplicate; it is
    # removed from the collection (delete-orphan), not deleted through the session.
    assert [(i.resource_id, i.position) for i in other.items] == [(31, 0), (20, 2)]
    assert session.deleted == []
    assert other.fingerprint == "20:31"


@pytest.mark.anyio
async def test_reroute_drops_candidate_that_collapses_below_two_members(user):
    # Approving A(18)+B(19)+C(20) -> D(31) fully subsumes a pending A(18)+B(19):
    # it would collapse to just [31], which can never be approved, so it is
    # deleted rather than left as a dead end.
    subset = FakeCandidate(
        id=5,
        status=MergeCandidateStatus.PENDING,
        items=[FakeItem(18, 0), FakeItem(19, 1)],
        fingerprint="18:19",
    )
    session = FakeSession(scalars_result=[subset])

    await mca._reroute_pending_candidates(
        session=session,
        user=user,
        merged_away_ids=[18, 19, 20],
        new_id=31,
    )

    assert session.deleted == [subset]
    assert subset.fingerprint == "18:19"  # untouched; row is being deleted


@pytest.mark.anyio
async def test_reroute_drops_duplicate_candidate_on_fingerprint_collision(user):
    # A(18)+C(20) and B(19)+C(20) both collapse to D(31)+C(20). The lower-id
    # candidate survives; the second is now the identical proposal and is deleted.
    ac = FakeCandidate(
        id=5,
        status=MergeCandidateStatus.PENDING,
        items=[FakeItem(18, 0), FakeItem(20, 1)],
        fingerprint="18:20",
    )
    bc = FakeCandidate(
        id=6,
        status=MergeCandidateStatus.PENDING,
        items=[FakeItem(19, 0), FakeItem(20, 1)],
        fingerprint="19:20",
    )
    session = FakeSession(scalars_result=[ac, bc])

    await mca._reroute_pending_candidates(
        session=session,
        user=user,
        merged_away_ids=[18, 19],
        new_id=31,
    )

    assert session.deleted == [bc]
    assert ac.fingerprint == "20:31"
    assert [i.resource_id for i in ac.items] == [31, 20]


@pytest.mark.anyio
async def test_reroute_is_noop_without_overlapping_candidates(user):
    session = FakeSession(scalars_result=[])

    await mca._reroute_pending_candidates(
        session=session,
        user=user,
        merged_away_ids=[18, 19],
        new_id=31,
    )

    assert session.deleted == []


@pytest.mark.anyio
async def test_deny_merge_candidate_rejects_non_pending(user):
    candidate = FakeCandidate(
        id=9,
        status=MergeCandidateStatus.DENIED,
        items=[FakeItem(18, 0), FakeItem(19, 1)],
    )
    session = FakeSession(scalar_result=candidate)

    with pytest.raises(InvalidActionError, match="is not pending"):
        await mca.deny_merge_candidate(session=session, user=user, candidate_id=9)


@pytest.mark.anyio
async def test_deny_merge_candidate_updates_candidate(monkeypatch, user):
    candidate = FakeCandidate(
        id=9,
        status=MergeCandidateStatus.PENDING,
        items=[FakeItem(18, 0), FakeItem(19, 1)],
    )
    session = FakeSession(scalar_result=candidate)

    view = await mca.deny_merge_candidate(
        session=session,
        user=user,
        candidate_id=9,
        request=MergeCandidateReviewRequest(review_notes="do not merge"),
    )

    assert candidate.status == MergeCandidateStatus.DENIED
    assert candidate.review_notes == "do not merge"
    assert candidate.reviewed_by_id == user.id
    assert candidate.last_updated_by_id == user.id
    assert session.flush_calls == 1
    assert view.status == MergeCandidateStatus.DENIED
    assert view.review_notes == "do not merge"


def _status_for(compare, field):
    return next(c.status for c in compare if c.field == field)


def _values_for(compare, field):
    entry = next(c for c in compare if c.field == field)
    return [(v.resource_id, v.source, v.source_id, v.value) for v in entry.values]


def test_build_comparison_status_is_match_or_different_per_resource():
    # status compares the resources' coalesced values (resource_views); values
    # list every contributing source, tagged with its resource_id.
    view_a = OilGasFieldBase(name="Ghawar", country="SAU", basin=None, region="R1")
    view_b = OilGasFieldBase(name="Burgan", country="SAU", basin=None, region=None)
    src_a = SimpleNamespace(source="rmi", id=10, name="Ghawar", country="SAU")
    src_b = SimpleNamespace(source="rmi", id=11, name="Burgan", country="SAU")
    sources_with_priority = [(18, src_a, 1), (19, src_b, 1)]

    compare = mca._build_comparison([view_a, view_b], sources_with_priority)

    # resources disagree
    assert _status_for(compare, "name") == "different"
    # resources agree
    assert _status_for(compare, "country") == "match"
    # both null -> agree
    assert _status_for(compare, "basin") == "match"
    # one resource has a value, the other is null -> different
    assert _status_for(compare, "region") == "different"

    # values are per-source (winner-first), tagged with the attached resource_id
    assert _values_for(compare, "name") == [
        (18, "rmi", 10, "Ghawar"),
        (19, "rmi", 11, "Burgan"),
    ]

    # every OilGasFieldBase field is represented, once, in field order
    assert [c.field for c in compare] == list(OilGasFieldBase.model_fields)


def test_build_comparison_matches_when_per_resource_winners_agree():
    # Composite resource A resolves basin to "Foo" (its RMI winner), with a
    # lower-priority GEM source "Bar" also in play. Resource B resolves basin to
    # "Foo". Three sources in play, but both resources' *winners* agree -> match:
    # status compares the resources' coalesced values, not every raw source.
    view_a = OilGasFieldBase(name=None, country="SAU", basin="Foo")
    view_b = OilGasFieldBase(name=None, country="SAU", basin="Foo")
    src_a_win = SimpleNamespace(source="rmi", id=10, basin="Foo")
    src_a_lose = SimpleNamespace(source="gem", id=11, basin="Bar")
    src_b = SimpleNamespace(source="rmi", id=12, basin="Foo")
    sources_with_priority = [(18, src_a_win, 1), (18, src_a_lose, 2), (19, src_b, 1)]

    compare = mca._build_comparison([view_a, view_b], sources_with_priority)

    assert _status_for(compare, "basin") == "match"
    # all three sources are listed (the losing "Bar" is not dropped), winner-first
    assert _values_for(compare, "basin") == [
        (18, "rmi", 10, "Foo"),
        (19, "rmi", 12, "Foo"),
        (18, "gem", 11, "Bar"),
    ]


def test_build_comparison_keeps_present_values_and_matches_equal():
    # Only None is dropped (unset); present values are kept and compared. Empty
    # strings can't be persisted (write-path skip + DB CHECK), so they never
    # reach here -- a null check is all `_build_comparison` needs.
    view_a = OilGasFieldBase(name=None, country="SAU", basin="Ghawar")
    view_b = OilGasFieldBase(name=None, country="SAU", basin="Ghawar")
    src_a = SimpleNamespace(source="rmi", id=10, basin="Ghawar")
    src_b = SimpleNamespace(source="rmi", id=11, basin="Ghawar")

    compare = mca._build_comparison([view_a, view_b], [(18, src_a, 1), (19, src_b, 1)])

    assert _values_for(compare, "basin") == [
        (18, "rmi", 10, "Ghawar"),
        (19, "rmi", 11, "Ghawar"),
    ]
    assert _status_for(compare, "basin") == "match"


@pytest.mark.anyio
async def test_get_merge_candidate_returns_detail_view_in_item_order(monkeypatch):
    candidate = FakeCandidate(
        id=1,
        status=MergeCandidateStatus.PENDING,
        items=[
            FakeItem(resource_id=19, position=1),
            FakeItem(resource_id=18, position=0),
        ],
    )

    async def fake_load_candidate_model(session_arg, candidate_id):
        assert candidate_id == 1
        return candidate

    async def fake_coalesce(session_arg, resource_ids, licensed):
        # ordered by item position
        assert resource_ids == [18, 19]
        assert licensed == ["gem"]
        return {
            rid: SimpleNamespace(
                source_data=[SimpleNamespace(source="rmi", id=rid, name=f"name-{rid}")],
                view=OilGasFieldBase(name=f"name-{rid}", country="USA"),
                provenance={"name": (f"name-{rid}", "rmi", rid)},
            )
            for rid in resource_ids
        }

    async def fake_default_priority(session_arg):
        return {"rmi": 1, "gem": 2, "wm": 3, "llm": 4}

    monkeypatch.setattr(mca, "_load_candidate_model", fake_load_candidate_model)
    monkeypatch.setattr(mca, "coalesce_resources_with_sources", fake_coalesce)
    monkeypatch.setattr(mca, "_default_source_priority", fake_default_priority)

    view = await mca.get_merge_candidate(
        AsyncMock(), candidate_id=1, licensed_sources=["gem"]
    )

    assert isinstance(view, MergeCandidateDetailView)
    assert view.resource_ids == [18, 19]
    assert view.name == "name-18"
    # resources detail objects are gone; compare carries the per-source values
    assert not hasattr(view, "resources")
    assert [c.field for c in view.compare] == list(OilGasFieldBase.model_fields)
    # each source value is tagged with the resource it is attached to
    name_values = next(c for c in view.compare if c.field == "name").values
    assert {(v.resource_id, v.value) for v in name_values} == {
        (18, "name-18"),
        (19, "name-19"),
    }


@pytest.mark.anyio
async def test_get_merge_candidate_after_merge_yields_empty_compare(monkeypatch):
    # Live behavior for an APPROVED candidate: originals are repointed with
    # memberships INACTIVE, so coalesce_resources returns null-shell views with
    # no surviving source data.
    candidate = FakeCandidate(
        id=2,
        status=MergeCandidateStatus.APPROVED,
        items=[FakeItem(18, 0), FakeItem(19, 1)],
        merged_resource_id=31,
    )

    async def fake_load_candidate_model(session_arg, candidate_id):
        return candidate

    async def fake_coalesce(session_arg, resource_ids, licensed):
        return {
            rid: SimpleNamespace(
                source_data=[],
                view=OilGasFieldBase(name=None, country=None),
                provenance={"name": None},
            )
            for rid in resource_ids
        }

    async def fake_coalesce_merged(session_arg, resource_ids, licensed):
        assert resource_ids == [31]
        return {31: _named("Merged")}

    async def fake_default_priority(session_arg):
        return {"rmi": 1, "gem": 2, "wm": 3, "llm": 4}

    monkeypatch.setattr(mca, "_load_candidate_model", fake_load_candidate_model)
    monkeypatch.setattr(mca, "coalesce_resources_with_sources", fake_coalesce)
    monkeypatch.setattr(mca, "_default_source_priority", fake_default_priority)
    monkeypatch.setattr(mca, "coalesce_resources", fake_coalesce_merged)

    view = await mca.get_merge_candidate(AsyncMock(), candidate_id=2)

    assert view.merged_resource_id == 31
    assert view.name == "Merged"
    # every resource is null on every field -> they all agree (match), no values
    assert all(c.status == "match" for c in view.compare)
    assert all(c.values == [] for c in view.compare)
