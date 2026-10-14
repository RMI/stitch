"""Build and maintain ``og_field_resource_state`` from the live coalescer.

Every stored row comes from ``queries.coalesced_winner_rows`` -- the same SQL
ranking the live list path hydrates with (through ``utils.coalesce_resources``)
-- run once per permission profile with that profile's exact source set. There
is no second ranking implementation, so cached state can't drift from live
coalescing. Rows hold the same materialized winning values the live path builds
its view from; like the live path, they are validated only when a list page is
built from them, so a stored value today's model rejects can't stop a rebuild
or a write.

* ``refresh_resource_states`` recomputes the given resources inside the caller's
  transaction: lock their rows, delete their state, and re-insert one row per
  profile for those still listable. A resource that stopped being listable (e.g.
  merged away) is left with no rows.
* ``rebuild_all_resource_state`` rebuilds everything in committed batches behind
  the readiness flag, so new readers stay on the live path until it fully
  succeeds. It never empties the table, so a reader already past the readiness
  check sees each resource's old or new rows, never a missing one.
* ``is_resource_state_ready`` checks the table can be used: a completed full
  rebuild, by the same commit as the running code. Any change to how rows are
  computed ships in a new commit, so deploying it switches reads to live until
  that code rebuilds the table. List reads go through
  ``is_resource_state_ready_for_reads``, which asks at most every few seconds.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Collection
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy import Select, delete, distinct, func, insert, or_, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from stitch.api.observability.context import named_query
from stitch.api.settings import get_settings

from ..model import OGFieldResourceState, OGFieldResourceStateStatus, ResourceModel
from ..model.og_field_resource_state import RESOURCE_STATE_STATUS_KEY
from ..model.oil_gas_field_source_value import ATTRIBUTE_NAMES, materialize_value
from ..queries import coalesced_winner_rows, resource_universe
from .permissions import PERMISSION_MASKS, visible_sources_for_mask

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE: Final[int] = 500

# Code version when the build sets no GIT_SHA (e.g. running the API directly on
# a developer machine). Deliberately not the local git HEAD: that would switch a
# local read model off on every commit.
UNKNOWN_CODE_VERSION: Final[str] = "unknown"

# List reads re-check readiness at most this often per API process. The table
# is never emptied and each process only trusts rows built by its own commit,
# so a briefly out-of-date answer only delays switching between the read model
# and live reads; it never serves a broken page.
READINESS_CACHE_SECONDS: Final[float] = 5.0

# Postgres advisory-lock key held for the duration of a full rebuild, so two
# rebuilds can't interleave. Arbitrary; only needs to be unique within the app.
_REBUILD_LOCK_KEY: Final[int] = 766_001

# How long a deploy's rebuild (``rebuild_resource_state_if_stale``) waits for a
# rebuild already holding the lock, and how often it checks.
DEFAULT_LOCK_WAIT: Final[timedelta] = timedelta(minutes=10)
_LOCK_POLL_SECONDS: Final[float] = 5.0

# Server-side TCP keepalives for the lock-holding connection: if the process
# running a rebuild vanishes without closing its connection (e.g. a cancelled CI
# job whose machine is torn down), Postgres ends the session -- releasing the
# lock -- after about a minute instead of the OS default of hours.
_KEEPALIVE_SETTINGS: Final[dict[str, str]] = {
    "tcp_keepalives_idle": "30",
    "tcp_keepalives_interval": "10",
    "tcp_keepalives_count": "3",
}


class ResourceStateRebuildError(RuntimeError):
    """A rebuild or repair could not run, or did not produce complete state."""


def lock_resources_statement(resource_ids: Collection[int]) -> Select[tuple[int]]:
    """``SELECT ... FOR UPDATE`` over the resource rows, in ascending id order.

    A stable order means two transactions locking overlapping sets (e.g. two
    merges) always queue in the same order instead of deadlocking.
    """
    return (
        select(ResourceModel.id)
        .where(ResourceModel.id.in_(sorted(set(resource_ids))))
        .order_by(ResourceModel.id)
        .with_for_update()
    )


async def lock_resources(session: AsyncSession, resource_ids: Collection[int]) -> None:
    """Lock the resource rows until the caller's transaction ends.

    Write actions take it at their start, before their own reads and inserts:
    those inserts' foreign keys take a weaker lock on the same row, and two
    writers that each hold that and then wait to upgrade it deadlock. Locked
    first, concurrent writers to a resource queue instead -- the second waits,
    then reads the first's committed changes, so neither overwrites the other
    with a stale recompute. ``refresh_resource_states`` locks again (a no-op
    when already held) to protect callers like the full rebuild. SQLite has no
    row locks (it already serializes writers), so this is a no-op there.
    """
    if resource_ids:
        await session.execute(lock_resources_statement(resource_ids))


def _empty_state_row(resource_id: int, mask: int) -> dict[str, Any]:
    """A row with every field (and its provenance) unset."""
    return {
        "resource_id": resource_id,
        "permission_mask": mask,
        **{field: None for field in ATTRIBUTE_NAMES},
        "provenance": {field: None for field in ATTRIBUTE_NAMES},
    }


async def _compute_state_rows(
    session: AsyncSession, resource_ids: list[int]
) -> list[dict[str, Any]]:
    """Rows for every ``(resource, profile)`` pair: one winner query per profile.

    Each winner's value is materialized exactly as the live path does before
    building its view, and its source key recorded as provenance. Fields with no
    winner stay unset.
    """
    rows: list[dict[str, Any]] = []
    for mask in PERMISSION_MASKS:
        by_id = {rid: _empty_state_row(rid, mask) for rid in resource_ids}
        winners = await session.execute(
            coalesced_winner_rows(resource_ids, visible_sources_for_mask(mask))
        )
        for rid, colname, value_text, value_num, value_json, source, _ in winners:
            row = by_id[rid]
            row[colname] = materialize_value(
                colname,
                value_text=value_text,
                value_num=value_num,
                value_json=value_json,
            )
            row["provenance"][colname] = source
        rows.extend(by_id.values())
    return rows


async def refresh_resource_states(
    session: AsyncSession, resource_ids: Collection[int]
) -> list[int]:
    """Make the given resources' stored state match authoritative data.

    Runs in the caller's transaction, so it commits (or rolls back) with the
    write that triggered it. Resources that are no longer listable end up with
    no rows; ids that don't exist are ignored. Returns the ids that were
    recomputed (the listable ones), in ascending order.

    Its queries are labeled ``read_model.refresh`` (rather than the calling
    write's label), so the cost the read model adds to writes and rebuilds can
    be seen on its own.
    """
    ids = sorted(set(resource_ids))
    if not ids:
        return []
    with named_query("read_model.refresh"):
        await lock_resources(session, ids)
        await session.execute(
            delete(OGFieldResourceState).where(
                OGFieldResourceState.resource_id.in_(ids)
            )
        )
        listable = sorted(
            (
                await session.scalars(
                    resource_universe().where(ResourceModel.id.in_(ids))
                )
            ).all()
        )
        if listable:
            await session.execute(
                insert(OGFieldResourceState),
                await _compute_state_rows(session, listable),
            )
    return listable


async def refresh_resource_state(session: AsyncSession, resource_id: int) -> None:
    """``refresh_resource_states`` for a single resource."""
    await refresh_resource_states(session, [resource_id])


def current_code_version() -> str:
    """The commit the running code was built from (``GIT_SHA``)."""
    return get_settings().git_sha or UNKNOWN_CODE_VERSION


async def is_resource_state_ready(session: AsyncSession) -> bool:
    """True only when a full rebuild by this same commit completed.

    A missing status row, a cleared flag, or rows built by other code (an older
    or newer deploy) all mean not ready.
    """
    status = (
        await session.execute(
            select(
                OGFieldResourceStateStatus.ready,
                OGFieldResourceStateStatus.code_version,
            ).where(OGFieldResourceStateStatus.key == RESOURCE_STATE_STATUS_KEY)
        )
    ).one_or_none()
    return (
        status is not None
        and status.ready is True
        and status.code_version == current_code_version()
    )


class _ReadinessCache:
    """This process's most recent readiness answer, and when it was checked."""

    def __init__(self) -> None:
        self.checked_at: float | None = None
        self.ready = False

    def fresh(self) -> bool:
        return (
            self.checked_at is not None
            and time.monotonic() - self.checked_at < READINESS_CACHE_SECONDS
        )

    def remember(self, ready: bool) -> None:
        self.checked_at = time.monotonic()
        self.ready = ready

    def forget(self) -> None:
        self.checked_at = None


_readiness_cache = _ReadinessCache()


async def is_resource_state_ready_for_reads(session: AsyncSession) -> bool:
    """``is_resource_state_ready``, asked at most every few seconds per process.

    For the list/filter-options read path, so most requests don't pay a round
    trip just to check readiness (see ``READINESS_CACHE_SECONDS``).
    """
    if not _readiness_cache.fresh():
        _readiness_cache.remember(await is_resource_state_ready(session))
    return _readiness_cache.ready


def forget_cached_readiness() -> None:
    """Make the next list read ask the database again."""
    _readiness_cache.forget()


async def _set_ready(session: AsyncSession, ready: bool) -> None:
    status = await session.get(OGFieldResourceStateStatus, RESOURCE_STATE_STATUS_KEY)
    if status is None:
        status = OGFieldResourceStateStatus(key=RESOURCE_STATE_STATUS_KEY, ready=ready)
        session.add(status)
    status.ready = ready
    if ready:
        status.rebuilt_at = datetime.now(UTC)
        status.code_version = current_code_version()


async def _delete_unlistable_state(session: AsyncSession) -> None:
    """Drop rows of resources that are no longer listable (e.g. merged away)."""
    universe = resource_universe().subquery()
    await session.execute(
        delete(OGFieldResourceState).where(
            OGFieldResourceState.resource_id.not_in(select(universe.c.resource_id))
        )
    )


async def _integrity_problems(session: AsyncSession) -> list[str]:
    """Ways the stored state fails to cover exactly the listable resources."""
    state = OGFieldResourceState
    universe = resource_universe().subquery()
    row_counts = (
        select(state.resource_id, func.count().label("n"))
        .group_by(state.resource_id)
        .subquery()
    )
    incomplete = await session.scalar(
        select(func.count())
        .select_from(
            universe.outerjoin(
                row_counts, row_counts.c.resource_id == universe.c.resource_id
            )
        )
        .where(or_(row_counts.c.n.is_(None), row_counts.c.n != len(PERMISSION_MASKS)))
    )
    unlistable = await session.scalar(
        select(func.count(distinct(state.resource_id))).where(
            state.resource_id.not_in(select(universe.c.resource_id))
        )
    )
    problems: list[str] = []
    if incomplete:
        problems.append(
            f"{incomplete} listable resource(s) lack a row for every permission profile"
        )
    if unlistable:
        problems.append(f"{unlistable} non-listable resource(s) have stored state")
    return problems


async def _drop_vanished_clients_quickly(conn: AsyncConnection) -> None:
    """Ask Postgres to notice quickly if this connection's client vanishes.

    Session settings, so they also apply if the pooled connection is reused --
    harmless (it only makes Postgres notice dead clients sooner).
    """
    for name, value in _KEEPALIVE_SETTINGS.items():
        await conn.execute(
            text("SELECT set_config(:name, :value, false)"),
            {"name": name, "value": value},
        )


@asynccontextmanager
async def _exclusive_rebuild(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    wait: timedelta | None = None,
) -> AsyncIterator[None]:
    """Hold a Postgres advisory lock so only one full rebuild runs at a time.

    Without ``wait``, fails at once if another rebuild holds the lock; with it,
    retries until the lock is free or ``wait`` has passed. Uses a session-level
    lock on an autocommit connection, so it neither holds a transaction open for
    the whole rebuild nor conflicts with the status row the rebuild updates.
    No-op on other dialects.
    """
    async with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            yield
            return
        conn = await session.connection(
            execution_options={"isolation_level": "AUTOCOMMIT"}
        )
        await _drop_vanished_clients_quickly(conn)
        give_up_at = time.monotonic() + (wait.total_seconds() if wait else 0)
        while not await conn.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": _REBUILD_LOCK_KEY}
        ):
            if time.monotonic() >= give_up_at:
                raise ResourceStateRebuildError(
                    "Another resource-state rebuild is already running."
                    + (f" Waited {wait} for it to finish." if wait else "")
                )
            logger.info("Waiting for another resource-state rebuild to finish.")
            await asyncio.sleep(_LOCK_POLL_SECONDS)
        try:
            yield
        finally:
            await conn.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": _REBUILD_LOCK_KEY}
            )


async def rebuild_all_resource_state(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Rebuild every listable resource's state; return how many were rebuilt.

    Fails at once if another rebuild is running. Each step commits on its own,
    so the table is never locked for the whole run. Readiness is cleared first,
    so new readers use the live path; it is set again only after every batch
    commits, rows of no-longer-listable resources are removed, and the integrity
    check passes. The table is never emptied: a reader that passed the readiness
    check just before the rebuild started still finds a row for every resource.
    A failure leaves readiness cleared; whatever rows remain are not served, and
    the next run replaces them. Write-path refreshes may run concurrently --
    both sides lock a resource before recomputing it.
    """
    _check_batch_size(batch_size)
    async with _exclusive_rebuild(session_factory):
        return await _rebuild_while_locked(session_factory, batch_size)


async def rebuild_resource_state_if_stale(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    lock_wait: timedelta = DEFAULT_LOCK_WAIT,
) -> int | None:
    """Rebuild unless the read model is already current for this code.

    The post-deploy step. Waits up to ``lock_wait`` for a rebuild already
    running, then checks again: if that rebuild (by the same commit) made the
    read model current, there is nothing to do. Returns how many resources were
    rebuilt, or ``None`` if it was already current.
    """
    _check_batch_size(batch_size)
    async with _exclusive_rebuild(session_factory, wait=lock_wait):
        async with session_factory() as session:
            if await is_resource_state_ready(session):
                return None
        return await _rebuild_while_locked(session_factory, batch_size)


def _check_batch_size(batch_size: int) -> None:
    if batch_size < 1:
        raise ValueError(f"batch_size must be at least 1, got {batch_size}")


async def _rebuild_while_locked(
    session_factory: async_sessionmaker[AsyncSession], batch_size: int
) -> int:
    """The full rebuild itself; the caller holds the rebuild lock.

    Forgets this process's cached readiness after each change commits, so reads
    here switch immediately (other processes switch within the cache window).
    """
    async with session_factory.begin() as session:
        await _set_ready(session, False)
    forget_cached_readiness()
    async with session_factory() as session:
        ids = list(
            (
                await session.scalars(resource_universe().order_by(ResourceModel.id))
            ).all()
        )

    for start in range(0, len(ids), batch_size):
        async with session_factory.begin() as session:
            await refresh_resource_states(session, ids[start : start + batch_size])
        logger.info(
            "Rebuilt resource state for %d of %d resources.",
            min(start + batch_size, len(ids)),
            len(ids),
        )

    async with session_factory.begin() as session:
        await _delete_unlistable_state(session)
        if problems := await _integrity_problems(session):
            raise ResourceStateRebuildError(
                "Resource-state rebuild failed its integrity check: "
                + "; ".join(problems)
            )
        await _set_ready(session, True)
    forget_cached_readiness()
    return len(ids)
