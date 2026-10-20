"""A full rebuild finishing while an ``--ids`` repair runs, on a real Postgres (opt-in).

The repair holds the status row shared for its whole transaction; the rebuild's
last check, and setting readiness, hold it exclusively. Whichever gets there
first, the table is never marked ready while holding a repair's rows from other
code: a repair already running is waited for and its rows redone, and a repair
starting later waits for readiness, then refuses because other code built the
table.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.api.db.model import OGFieldResourceState, OGFieldResourceStateStatus
from stitch.api.db.read_model import rebuild as rebuild_cli
from stitch.api.db.read_model import state
from stitch.api.db.read_model.state import (
    ResourceStateRebuildError,
    rebuild_all_resource_state,
)
from stitch.api.entities import User
from stitch.api.settings import get_settings

from .dataset import attach, new_resource
from .postgres import requires_postgres

pytestmark = [pytest.mark.anyio, requires_postgres]

type SessionFactory = async_sessionmaker[AsyncSession]


@pytest.fixture(autouse=True)
def _rebuild_runs_commit_b(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_SHA", "commit-b")
    get_settings.cache_clear()


async def _seed(factory: SessionFactory, user: User) -> list[int]:
    ids = []
    async with factory.begin() as session:
        for i in range(3):
            rid = await new_resource(session, user)
            await attach(session, user, rid, "gem", name=f"Seed {i}", country="USA")
            ids.append(rid)
    return ids


def _pause_at_final_check(
    monkeypatch: pytest.MonkeyPatch, *, after_locking: bool
) -> tuple[asyncio.Event, asyncio.Event]:
    """Pause the rebuild the first time it reaches its final, locked check,
    just before (or just after) it takes the status row lock."""
    paused, resume = asyncio.Event(), asyncio.Event()
    real_lock: Callable[[AsyncSession], Awaitable[None]] = state._lock_status_row
    calls = 0

    async def pausing_lock(session: AsyncSession) -> None:
        nonlocal calls
        calls += 1
        if calls > 1:
            await real_lock(session)
            return
        if after_locking:
            await real_lock(session)
        paused.set()
        await resume.wait()
        if not after_locking:
            await real_lock(session)

    monkeypatch.setattr(state, "_lock_status_row", pausing_lock)
    return paused, resume


async def _row_versions(factory: SessionFactory) -> set[str | None]:
    async with factory() as session:
        return set(
            (await session.scalars(select(OGFieldResourceState.code_version))).all()
        )


async def _status(factory: SessionFactory):
    async with factory() as session:
        return (
            await session.execute(select(OGFieldResourceStateStatus.__table__))
        ).one()


async def test_repair_already_running_is_waited_for_and_redone(
    pg_session_factory: SessionFactory,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    ids = await _seed(pg_session_factory, test_user)
    paused, resume = _pause_at_final_check(monkeypatch, after_locking=False)
    rebuild = asyncio.create_task(rebuild_all_resource_state(pg_session_factory))
    await asyncio.wait_for(paused.wait(), timeout=30)

    # An --ids repair from the old image (commit-a): its guard allows it, since
    # the rebuild cleared readiness, and it rewrites a resource's rows with the
    # old code but hasn't committed yet.
    async with pg_session_factory.begin() as repair:
        await rebuild_cli._refuse_if_served_by_other_code(repair)
        await repair.execute(
            update(OGFieldResourceState)
            .where(OGFieldResourceState.resource_id == ids[0])
            .values(name="Old code's answer", code_version="commit-a")
        )
        resume.set()
        await asyncio.sleep(0.5)
        assert not rebuild.done(), "the rebuild didn't wait for the running repair"

    # The repair committed; the rebuild sees its rows and redoes them.
    assert await asyncio.wait_for(rebuild, timeout=30) == len(ids) + 1
    status = await _status(pg_session_factory)
    assert (status.ready, status.code_version) == (True, "commit-b")
    assert await _row_versions(pg_session_factory) == {"commit-b"}
    async with pg_session_factory() as session:
        assert (
            await session.scalar(
                select(OGFieldResourceState.name).where(
                    OGFieldResourceState.resource_id == ids[0],
                    OGFieldResourceState.permission_mask == 0,
                )
            )
            == "Seed 0"
        )


async def test_repair_starting_later_waits_then_refuses(
    pg_session_factory: SessionFactory,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    ids = await _seed(pg_session_factory, test_user)
    paused, resume = _pause_at_final_check(monkeypatch, after_locking=True)
    rebuild = asyncio.create_task(rebuild_all_resource_state(pg_session_factory))
    await asyncio.wait_for(paused.wait(), timeout=30)

    # The rebuild holds the status row; an --ids repair from the old image
    # starts now.
    monkeypatch.setattr(rebuild_cli, "current_code_version", lambda: "commit-a")
    repair = asyncio.create_task(rebuild_cli._repair(pg_session_factory, [ids[0]]))
    await asyncio.sleep(0.5)
    assert not repair.done(), "the repair didn't wait for the rebuild to finish"

    resume.set()
    await asyncio.wait_for(rebuild, timeout=30)
    with pytest.raises(ResourceStateRebuildError, match="built by code commit-b"):
        await asyncio.wait_for(repair, timeout=30)

    status = await _status(pg_session_factory)
    assert (status.ready, status.code_version) == (True, "commit-b")
    assert await _row_versions(pg_session_factory) == {"commit-b"}
