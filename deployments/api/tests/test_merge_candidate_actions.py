from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from stitch.api.entities import (
    MergeCandidateCreateRequest,
    MergeCandidateReviewRequest,
    MergeCandidateStatus,
)
from stitch.api.db.errors import InvalidActionError, ResourceNotFoundError
from stitch.api.db import merge_candidate_actions as mca

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
    added: list[object] = field(default_factory=list)
    added_all: list[object] = field(default_factory=list)
    flush_calls: int = 0
    refresh_calls: list[tuple[object, object | None]] = field(default_factory=list)

    async def scalar(self, _stmt):
        return self.scalar_result

    async def scalars(self, _stmt):
        return SimpleNamespace(all=lambda: list(self.scalars_result))

    def add(self, obj):
        self.added.append(obj)

    def add_all(self, objs):
        self.added_all.extend(list(objs))

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


@pytest.mark.anyio
async def test_list_merge_candidates_returns_views_in_query_order():
    first = FakeCandidate(
        id=2,
        status=MergeCandidateStatus.PENDING,
        items=[FakeItem(18, 0), FakeItem(19, 1)],
    )
    second = FakeCandidate(
        id=1,
        status=MergeCandidateStatus.DENIED,
        items=[FakeItem(20, 0), FakeItem(21, 1)],
    )
    session = FakeSession(scalars_result=[first, second])

    views = await mca.list_merge_candidates(session)

    assert [view.id for view in views] == [2, 1]
    assert views[0].resource_ids == [18, 19]
    assert views[1].status == MergeCandidateStatus.DENIED


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
