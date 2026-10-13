"""The lock that keeps full rebuilds from overlapping, on a real Postgres (opt-in).

A deploy's ``--if-stale`` rebuild waits for a rebuild already holding the lock,
then rebuilds only if the read model is still stale. The lock-holding connection
asks Postgres to notice a vanished client quickly, so a rebuild whose machine
disappears (e.g. a cancelled CI job) doesn't hold the lock for hours.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from stitch.api.db.model import OGFieldResourceStateStatus
from stitch.api.db.read_model import state
from stitch.api.db.read_model.state import (
    ResourceStateRebuildError,
    is_resource_state_ready,
    rebuild_all_resource_state,
    rebuild_resource_state_if_stale,
)
from stitch.api.entities import User

from .dataset import attach, new_resource
from .postgres import requires_postgres

pytestmark = [pytest.mark.anyio, requires_postgres]

type SessionFactory = async_sessionmaker[AsyncSession]


@pytest.fixture(autouse=True)
def _poll_quickly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(state, "_LOCK_POLL_SECONDS", 0.05)


async def _seed(factory: SessionFactory, user: User, count: int = 3) -> None:
    async with factory.begin() as session:
        for i in range(count):
            rid = await new_resource(session, user)
            await attach(session, user, rid, "gem", name=f"Seed {i}", country="USA")


@asynccontextmanager
async def _another_rebuild_holds_the_lock(
    factory: SessionFactory,
) -> AsyncIterator[AsyncConnection]:
    engine = factory.kw["bind"]
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(
            text("SELECT pg_advisory_lock(:key)"), {"key": state._REBUILD_LOCK_KEY}
        )
        try:
            yield conn
        finally:
            await conn.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": state._REBUILD_LOCK_KEY},
            )


async def _rebuilt_at(factory: SessionFactory):
    async with factory() as session:
        return await session.scalar(select(OGFieldResourceStateStatus.rebuilt_at))


async def test_if_stale_waits_for_a_running_rebuild_then_rebuilds(
    pg_session_factory: SessionFactory, test_user: User
):
    await _seed(pg_session_factory, test_user)

    async with _another_rebuild_holds_the_lock(pg_session_factory):
        rebuild = asyncio.create_task(
            rebuild_resource_state_if_stale(
                pg_session_factory, lock_wait=timedelta(seconds=30)
            )
        )
        await asyncio.sleep(0.5)
        assert not rebuild.done(), "gave up instead of waiting for the lock"

    assert await asyncio.wait_for(rebuild, timeout=30) == 3
    async with pg_session_factory() as session:
        assert await is_resource_state_ready(session)


async def test_if_stale_skips_when_the_rebuild_it_waited_for_made_it_current(
    pg_session_factory: SessionFactory, test_user: User
):
    await _seed(pg_session_factory, test_user)

    async with _another_rebuild_holds_the_lock(pg_session_factory):
        rebuild = asyncio.create_task(
            rebuild_resource_state_if_stale(
                pg_session_factory, lock_wait=timedelta(seconds=30)
            )
        )
        await asyncio.sleep(0.2)
        # The other rebuild (same commit) finishes while we wait.
        async with pg_session_factory.begin() as session:
            await state._set_ready(session, True)
        finished_at = await _rebuilt_at(pg_session_factory)

    assert await asyncio.wait_for(rebuild, timeout=30) is None
    assert await _rebuilt_at(pg_session_factory) == finished_at


async def test_if_stale_gives_up_after_waiting_its_limit(
    pg_session_factory: SessionFactory, test_user: User
):
    await _seed(pg_session_factory, test_user)

    async with _another_rebuild_holds_the_lock(pg_session_factory):
        with pytest.raises(ResourceStateRebuildError, match="already running"):
            await rebuild_resource_state_if_stale(
                pg_session_factory, lock_wait=timedelta(seconds=0.5)
            )


async def test_full_rebuild_still_fails_straight_away(
    pg_session_factory: SessionFactory, test_user: User
):
    await _seed(pg_session_factory, test_user)

    async with _another_rebuild_holds_the_lock(pg_session_factory):
        started = time.monotonic()
        with pytest.raises(ResourceStateRebuildError, match="already running"):
            await rebuild_all_resource_state(pg_session_factory)
        assert time.monotonic() - started < 1


async def test_lock_connection_asks_postgres_to_drop_vanished_clients_quickly(
    pg_session_factory: SessionFactory,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    """The connection holding the lock has short server-side TCP keepalives, so
    Postgres ends its session (releasing the lock) soon after its client
    vanishes, rather than after the OS default of hours."""
    await _seed(pg_session_factory, test_user)
    applied: list[dict[str, object]] = []
    real_configure = state._drop_vanished_clients_quickly

    async def spy_configure(conn: AsyncConnection) -> None:
        await real_configure(conn)
        rows = await conn.execute(
            text(
                "SELECT name, setting FROM pg_settings WHERE name IN "
                "('tcp_keepalives_idle', 'tcp_keepalives_interval', "
                "'tcp_keepalives_count')"
            )
        )
        settings: dict[str, object] = {name: value for name, value in rows}
        settings["pid"] = await conn.scalar(text("SELECT pg_backend_pid()"))
        applied.append(settings)

    lock_holders: list[int] = []
    real_rebuild = state._rebuild_while_locked

    async def record_lock_holder(factory: SessionFactory, batch_size: int) -> int:
        async with factory() as session:
            lock_holders.append(
                await session.scalar(
                    text(
                        "SELECT pid FROM pg_locks WHERE locktype = 'advisory' "
                        "AND objid = :key AND granted"
                    ),
                    {"key": state._REBUILD_LOCK_KEY},
                )
            )
        return await real_rebuild(factory, batch_size)

    monkeypatch.setattr(state, "_drop_vanished_clients_quickly", spy_configure)
    monkeypatch.setattr(state, "_rebuild_while_locked", record_lock_holder)
    await rebuild_all_resource_state(pg_session_factory)

    [settings] = applied
    assert {k: v for k, v in settings.items() if k != "pid"} == {
        "tcp_keepalives_idle": "30",
        "tcp_keepalives_interval": "10",
        "tcp_keepalives_count": "3",
    }
    assert lock_holders == [settings["pid"]]
