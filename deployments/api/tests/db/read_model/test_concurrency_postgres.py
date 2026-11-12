"""The write paths' row locks, on a real Postgres (opt-in).

SQLite serializes all writers and has no row locks, so the always-on tests
(``test_mutations``) can only check *when* each write takes its lock. These
check what the locks do (opt-in, see ``postgres.py``):

* a merge that waited on another re-reads its resources, so it sees they were
  already merged (SQLite can't show a stale read);
* the lock is ``FOR NO KEY UPDATE``, so it never conflicts with the key-share
  locks that inserting rows referencing a resource takes -- with ``FOR UPDATE``,
  creating a merge candidate during a merge deadlocks;
* an attach queued behind a merge of its resource refuses once the merge
  commits.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db import og_field_source_actions as source_actions
from stitch.api.db.errors import ResourceIntegrityError
from stitch.api.db.merge_candidate_actions import _fingerprint
from stitch.api.db.model import (
    MergeCandidateItemModel,
    MergeCandidateModel,
    ResourceModel,
)
from stitch.api.db.read_model.state import refresh_resource_states
from stitch.api.entities import User
from stitch.ogsi.model import RMISource

from tests.utils import make_source_record

from .dataset import attach, dump_state, new_resource
from .postgres import requires_postgres

pytestmark = [pytest.mark.anyio, requires_postgres]

# How long a writer must stay blocked to count as waiting on the other's lock.
_BLOCKED_FOR_SECONDS = 0.5

type SessionFactory = async_sessionmaker[AsyncSession]


async def _seed_resources(factory: SessionFactory, user: User, count: int) -> list[int]:
    """``count`` listable resources, each with one gem source and current state."""
    async with factory.begin() as session:
        ids = []
        for i in range(count):
            rid = await new_resource(session, user)
            await attach(session, user, rid, "gem", name=f"Seed {i}", country="USA")
            ids.append(rid)
        await refresh_resource_states(session, ids)
    return ids


async def _assert_matches_recompute(factory: SessionFactory) -> None:
    async with factory() as session:
        maintained = await dump_state(session)
        all_ids = (await session.scalars(select(ResourceModel.id))).all()
        await refresh_resource_states(session, all_ids)
        assert await dump_state(session) == maintained
        await session.rollback()


async def _attach_in_own_transaction(
    factory: SessionFactory, user: User, rid: int, source: RMISource
) -> None:
    async with factory.begin() as session:
        await source_actions.create_and_attach_source(session, user, source, rid)


async def test_overlapping_merges_in_opposite_order_serialize(
    pg_session_factory: SessionFactory, test_user: User
):
    """Locking in id order means two merges sharing resources queue instead of
    deadlocking, and the second sees the first already merged them."""
    a, b, c = await _seed_resources(pg_session_factory, test_user, 3)

    async with pg_session_factory() as first, pg_session_factory() as second:
        # The second session already holds a (soon stale) copy of ``b``, as the
        # merge-candidate approval path does before merging.
        stale_b = await second.get(ResourceModel, b)
        assert stale_b is not None and stale_b.repointed_id is None

        await resource_actions.apply_resource_merge(first, test_user, [a, b])
        second_merge = asyncio.create_task(
            resource_actions.apply_resource_merge(second, test_user, [c, b])
        )
        await asyncio.sleep(_BLOCKED_FOR_SECONDS)
        assert not second_merge.done()
        await first.commit()

        with pytest.raises(ResourceIntegrityError, match="already been merged"):
            await second_merge
        assert stale_b.repointed_id is not None  # re-read, not the stale copy
        await second.rollback()

    async with pg_session_factory() as session:
        stored_ids = {rid for rid, _ in await dump_state(session)}
    assert a not in stored_ids and b not in stored_ids
    assert c in stored_ids
    await _assert_matches_recompute(pg_session_factory)


async def test_merge_candidate_creation_and_a_merge_in_opposite_order_do_not_deadlock(
    pg_session_factory: SessionFactory, test_user: User
):
    """Creating a merge candidate inserts its items in request order, each
    taking a key-share lock on its resource; a merge locks its resources in id
    order. A merge lock that conflicted with key-share (``FOR UPDATE``) would
    deadlock here: the merge holds ``a`` and waits on ``b``, while the creation
    holds ``b`` and waits on ``a``."""
    a, b = await _seed_resources(pg_session_factory, test_user, 2)

    async with pg_session_factory.begin() as creating:
        candidate = MergeCandidateModel.create(
            created_by=test_user, fingerprint=_fingerprint([b, a])
        )
        creating.add(candidate)
        await creating.flush()
        creating.add(
            MergeCandidateItemModel(
                merge_candidate_id=candidate.id, resource_id=b, position=0
            )
        )
        await creating.flush()

        async def merge() -> None:
            async with pg_session_factory.begin() as merging:
                await resource_actions.apply_resource_merge(merging, test_user, [a, b])

        merging = asyncio.create_task(merge())
        await asyncio.sleep(_BLOCKED_FOR_SECONDS)
        creating.add(
            MergeCandidateItemModel(
                merge_candidate_id=candidate.id, resource_id=a, position=1
            )
        )
        await creating.flush()

    await asyncio.wait_for(merging, timeout=30)
    async with pg_session_factory() as session:
        stored_ids = {rid for rid, _ in await dump_state(session)}
    assert a not in stored_ids and b not in stored_ids
    await _assert_matches_recompute(pg_session_factory)


async def test_attach_waiting_on_a_merge_sees_the_resource_was_merged(
    pg_session_factory: SessionFactory, test_user: User
):
    """An attach queued behind a merge of its resource re-reads it after the
    merge commits and refuses, instead of attaching to a merged-away resource
    whose memberships would never be listed."""
    a, b = await _seed_resources(pg_session_factory, test_user, 2)

    async with pg_session_factory() as merging:
        await resource_actions.apply_resource_merge(merging, test_user, [a, b])
        attaching = asyncio.create_task(
            _attach_in_own_transaction(
                pg_session_factory,
                test_user,
                a,
                RMISource(
                    name="Late", country="USA", source_record=make_source_record()
                ),
            )
        )
        await asyncio.sleep(_BLOCKED_FOR_SECONDS)
        assert not attaching.done()
        await merging.commit()

    with pytest.raises(ResourceIntegrityError, match="has been merged"):
        await attaching
    await _assert_matches_recompute(pg_session_factory)
