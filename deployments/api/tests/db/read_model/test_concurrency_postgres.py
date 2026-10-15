"""Concurrent writes to the same resource, on a real Postgres (opt-in).

Every write recomputes its resource's read-model rows in its own transaction.
Without the per-resource row lock, two concurrent writers would each recompute
from a snapshot missing the other's change, and the second insert would collide
with the first's rows. The lock is taken at the *start* of each write, so a
writer that waited reads the other's committed changes (e.g. a merge), and it
is ``FOR NO KEY UPDATE`` so it never conflicts with the key-share locks that
inserting rows referencing a resource takes (which would deadlock). SQLite
serializes all writers and has no row locks, so this can only be exercised on
Postgres (opt-in, see ``postgres.py``).
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
from stitch.api.db.read_model import state
from stitch.api.db.read_model.state import refresh_resource_states
from stitch.api.entities import User
from stitch.ogsi.model import RMISource, WoodMacSource

from tests.utils import make_source_record

from .dataset import attach, dump_state, new_resource
from .postgres import requires_postgres
from .scenarios import rebuild_with_writes_midway

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


async def _concurrent_attaches(factory: SessionFactory, user: User, rid: int) -> bool:
    """Attach a source to ``rid`` in two overlapping transactions.

    The first finishes its write (and recompute) but holds its transaction open;
    the second starts, then the first commits. Returns whether the second was
    still waiting when the first committed.
    """
    async with factory() as first, factory() as second:
        await source_actions.create_and_attach_source(
            first,
            user,
            RMISource(
                name="From RMI", country="USA", source_record=make_source_record()
            ),
            rid,
        )
        second_write = asyncio.create_task(
            source_actions.create_and_attach_source(
                second,
                user,
                WoodMacSource(
                    name="From WM", country="USA", source_record=make_source_record()
                ),
                rid,
            )
        )
        await asyncio.sleep(_BLOCKED_FOR_SECONDS)
        second_was_waiting = not second_write.done()
        await first.commit()
        await second_write
        await second.commit()
    return second_was_waiting


async def test_concurrent_writes_to_one_resource_serialize(
    pg_session_factory: SessionFactory, test_user: User
):
    [rid] = await _seed_resources(pg_session_factory, test_user, 1)

    assert await _concurrent_attaches(pg_session_factory, test_user, rid)

    # The second writer recomputed after seeing the first's committed source, so
    # the stored state reflects both writes.
    async with pg_session_factory() as session:
        stored = await dump_state(session)
    assert stored[(rid, 0)]["name"] == "From RMI"  # wm hidden; rmi > gem
    assert stored[(rid, 2)]["provenance"]["name"] == "rmi"  # rmi > wm > gem
    await _assert_matches_recompute(pg_session_factory)


async def test_without_the_lock_concurrent_writes_collide(
    pg_session_factory: SessionFactory,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    """Shows concurrent writers really race: with the locks removed, two writers
    that refresh together each miss the other's rows, and the second insert
    collides with the first's."""
    [rid] = await _seed_resources(pg_session_factory, test_user, 1)

    async def no_lock(*_args: object, **_kwargs: object) -> None:
        return None

    for module in (state, source_actions):
        monkeypatch.setattr(module, "lock_resources", no_lock)
    # Without locks neither writer waits on the other, so both always arrive:
    # wait long enough that machine load can't make them miss each other.
    _hold_writers_before_refresh(monkeypatch, _Rendezvous(timeout=30))
    with pytest.raises(IntegrityError):
        await asyncio.gather(
            _attach_in_own_transaction(
                pg_session_factory,
                test_user,
                rid,
                RMISource(
                    name="From RMI", country="USA", source_record=make_source_record()
                ),
            ),
            _attach_in_own_transaction(
                pg_session_factory,
                test_user,
                rid,
                WoodMacSource(
                    name="From WM", country="USA", source_record=make_source_record()
                ),
            ),
        )


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


class _Rendezvous:
    """Holds each writer just before its read-model refresh until the other
    writer gets there too (or ``timeout`` passes), so both have finished their
    own inserts before either refreshes -- the interleaving most likely to
    deadlock if a writer's lock conflicted with its inserts' key-share locks
    (e.g. ``FOR UPDATE`` taken only at refresh time).

    The timeout lets a writer carry on when the other is (correctly) waiting on
    its lock; under heavy machine load a short one can let the writers miss
    each other, which makes a deadlock regression pass rather than fail.
    """

    def __init__(self, parties: int = 2, timeout: float = 1.0) -> None:
        self._parties = parties
        self._timeout = timeout
        self._arrived = 0
        self._all_arrived = asyncio.Event()

    async def arrive(self) -> None:
        self._arrived += 1
        if self._arrived >= self._parties:
            self._all_arrived.set()
        try:
            await asyncio.wait_for(self._all_arrived.wait(), self._timeout)
        except TimeoutError:
            pass  # The other writer is waiting on our lock; carry on.


def _hold_writers_before_refresh(
    monkeypatch: pytest.MonkeyPatch, rendezvous: _Rendezvous
) -> None:
    for module in (source_actions, resource_actions):
        real_refresh = module.refresh_resource_state

        async def held(session: AsyncSession, resource_id: int, _real=real_refresh):
            await rendezvous.arrive()
            await _real(session, resource_id)

        monkeypatch.setattr(module, "refresh_resource_state", held)


async def _attach_in_own_transaction(
    factory: SessionFactory, user: User, rid: int, source: RMISource | WoodMacSource
) -> None:
    async with factory.begin() as session:
        await source_actions.create_and_attach_source(session, user, source, rid)


async def _reverse_order_in_own_transaction(
    factory: SessionFactory, user: User, rid: int, field: str
) -> None:
    async with factory.begin() as session:
        current = await resource_actions.field_source_values(session, rid, field)
        await resource_actions.set_field_source_priority(
            session, user, rid, field, [view.source_id for view in reversed(current)]
        )


async def _seed_resource_with_competing_sources(
    factory: SessionFactory, user: User
) -> int:
    """A resource whose gem and rmi sources both carry ``name`` and ``country``."""
    async with factory.begin() as session:
        rid = await new_resource(session, user)
        await attach(session, user, rid, "gem", name="GEM name", country="USA")
        await attach(session, user, rid, "rmi", name="RMI name", country="CAN")
        await refresh_resource_states(session, [rid])
    return rid


async def test_writers_that_both_insert_before_refreshing_do_not_deadlock(
    pg_session_factory: SessionFactory,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    [rid] = await _seed_resources(pg_session_factory, test_user, 1)
    _hold_writers_before_refresh(monkeypatch, _Rendezvous())

    await asyncio.gather(
        _attach_in_own_transaction(
            pg_session_factory,
            test_user,
            rid,
            RMISource(
                name="From RMI", country="USA", source_record=make_source_record()
            ),
        ),
        _attach_in_own_transaction(
            pg_session_factory,
            test_user,
            rid,
            WoodMacSource(
                name="From WM", country="USA", source_record=make_source_record()
            ),
        ),
    )

    await _assert_matches_recompute(pg_session_factory)


async def test_attach_and_reprioritize_together_do_not_deadlock(
    pg_session_factory: SessionFactory,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    rid = await _seed_resource_with_competing_sources(pg_session_factory, test_user)
    _hold_writers_before_refresh(monkeypatch, _Rendezvous())

    await asyncio.gather(
        # No `name`, so the reprioritized field's eligible sources don't change.
        _attach_in_own_transaction(
            pg_session_factory,
            test_user,
            rid,
            WoodMacSource(name=None, country="USA", source_record=make_source_record()),
        ),
        _reverse_order_in_own_transaction(pg_session_factory, test_user, rid, "name"),
    )

    async with pg_session_factory() as session:
        stored = await dump_state(session)
    assert stored[(rid, 0)]["name"] == "GEM name"  # reordered: gem now first
    await _assert_matches_recompute(pg_session_factory)


async def test_two_reprioritizations_together_do_not_deadlock(
    pg_session_factory: SessionFactory,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    rid = await _seed_resource_with_competing_sources(pg_session_factory, test_user)
    _hold_writers_before_refresh(monkeypatch, _Rendezvous())

    # Different fields, so the two writes don't conflict for any other reason.
    await asyncio.gather(
        _reverse_order_in_own_transaction(pg_session_factory, test_user, rid, "name"),
        _reverse_order_in_own_transaction(
            pg_session_factory, test_user, rid, "country"
        ),
    )

    async with pg_session_factory() as session:
        stored = await dump_state(session)
    assert stored[(rid, 0)]["name"] == "GEM name"
    assert stored[(rid, 0)]["country"] == "USA"
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
        attach = asyncio.create_task(
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
        assert not attach.done()
        await merging.commit()

    with pytest.raises(ResourceIntegrityError, match="has been merged"):
        await attach
    await _assert_matches_recompute(pg_session_factory)


async def test_writes_midway_through_a_rebuild(
    pg_session_factory: SessionFactory,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    await rebuild_with_writes_midway(pg_session_factory, test_user, monkeypatch)
