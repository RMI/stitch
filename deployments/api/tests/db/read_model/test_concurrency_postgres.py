"""Concurrent writes to the same resource, on a real Postgres (opt-in).

Every write recomputes its resource's read-model rows in its own transaction.
Without the per-resource row lock, two concurrent writers would each recompute
from a snapshot missing the other's change, and the second insert would collide
with the first's rows. SQLite serializes all writers and ignores ``FOR UPDATE``,
so this can only be exercised on Postgres.

Skipped unless ``STITCH_TEST_POSTGRES_URL`` points at a disposable database::

    STITCH_TEST_POSTGRES_URL=postgresql+psycopg://postgres:pg@127.0.0.1:55432/stitch

Each test creates its own schema, builds the tables there, and drops it after;
existing tables in that database are not touched.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db import og_field_source_actions as source_actions
from stitch.api.db.errors import ResourceIntegrityError
from stitch.api.db.model import (
    OGFieldSourcePriority,
    ResourceModel,
    StitchBase,
    UserModel,
)
from stitch.api.db.read_model import state
from stitch.api.db.read_model.state import refresh_resource_states
from stitch.api.entities import User
from stitch.ogsi.model import SOURCE_PRIORITY, RMISource, WoodMacSource

from tests.utils import make_source_record

from .dataset import attach, dump_state, new_resource

_POSTGRES_URL = os.environ.get("STITCH_TEST_POSTGRES_URL")

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        not _POSTGRES_URL, reason="set STITCH_TEST_POSTGRES_URL to run Postgres tests"
    ),
]

# How long a writer must stay blocked to count as waiting on the other's lock.
_BLOCKED_FOR_SECONDS = 0.5

type SessionFactory = async_sessionmaker[AsyncSession]


@pytest.fixture
async def pg_session_factory(
    test_user_model: UserModel,
) -> AsyncIterator[SessionFactory]:
    assert _POSTGRES_URL is not None
    schema = f"stit766_test_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(_POSTGRES_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        _POSTGRES_URL, connect_args={"options": f"-csearch_path={schema}"}
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(StitchBase.metadata.create_all)
            await conn.execute(
                insert(OGFieldSourcePriority),
                [
                    {"source": source, "priority": i + 1}
                    for i, source in enumerate(SOURCE_PRIORITY)
                ],
            )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory.begin() as session:
            session.add(test_user_model)
        yield factory
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


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
    """Shows the scenario above really races: with the lock removed, the second
    writer's recompute misses the first's rows and its insert fails."""
    [rid] = await _seed_resources(pg_session_factory, test_user, 1)

    async def no_lock(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(state, "lock_resources", no_lock)
    with pytest.raises(IntegrityError):
        await _concurrent_attaches(pg_session_factory, test_user, rid)


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
