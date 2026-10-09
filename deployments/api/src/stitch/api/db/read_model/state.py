"""Build and maintain ``og_field_resource_state`` from the live coalescer.

Every stored row comes from ``utils.coalesce_resources`` -- the same function the
live list path hydrates with -- called once per permission profile with that
profile's exact source set. There is no second ranking implementation, so cached
state can't drift from live coalescing.

* ``refresh_resource_states`` recomputes the given resources inside the caller's
  transaction: lock their rows, delete their state, and re-insert one row per
  profile for those still listable. A resource that stopped being listable (e.g.
  merged away) is left with no rows.
* ``rebuild_all_resource_state`` rebuilds everything in committed batches behind
  the readiness flag, so readers stay on the live path until it fully succeeds.
* ``is_resource_state_ready`` is the flag readers check before using the table.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Collection
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import Select, delete, distinct, func, insert, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.ogsi.model import OGFieldResource

from ..model import OGFieldResourceState, OGFieldResourceStateStatus, ResourceModel
from ..model.og_field_resource_state import RESOURCE_STATE_STATUS_KEY
from ..model.oil_gas_field_source_value import ATTRIBUTE_NAMES
from ..queries import resource_universe
from ..utils import coalesce_resources
from .permissions import PERMISSION_MASKS, visible_sources_for_mask

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE: Final[int] = 500

# Postgres advisory-lock key held for the duration of a full rebuild, so two
# rebuilds can't interleave. Arbitrary; only needs to be unique within the app.
_REBUILD_LOCK_KEY: Final[int] = 766_001


class ResourceStateRebuildError(RuntimeError):
    """A full rebuild could not run or did not produce complete state."""


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

    Taken *before* reading anything to recompute, so concurrent writers to the
    same resource serialize: the second waits, then reads the first's committed
    changes, and neither overwrites the other with a stale recompute. SQLite has
    no row locks (it already serializes writers), so this is a no-op there.
    """
    if resource_ids:
        await session.execute(lock_resources_statement(resource_ids))


def _state_row(
    resource_id: int, mask: int, resource: OGFieldResource
) -> dict[str, Any]:
    """One table row from a live-coalesced resource.

    Stores each winner's materialized value -- exactly what the live path passes
    to ``OilGasFieldBase`` -- and its source key as provenance.
    """
    row: dict[str, Any] = {
        "resource_id": resource_id,
        "permission_mask": mask,
        **{field: None for field in ATTRIBUTE_NAMES},
    }
    provenance: dict[str, str | None] = {field: None for field in ATTRIBUTE_NAMES}
    for field, winner in resource.provenance.items():
        if winner is not None:
            value, source, _source_pk = winner
            row[field] = value
            provenance[field] = source
    row["provenance"] = provenance
    return row


async def _compute_state_rows(
    session: AsyncSession, resource_ids: list[int]
) -> list[dict[str, Any]]:
    """Rows for every ``(resource, profile)`` pair: one live coalesce per profile."""
    rows: list[dict[str, Any]] = []
    for mask in PERMISSION_MASKS:
        coalesced = await coalesce_resources(
            session, resource_ids, visible_sources_for_mask(mask)
        )
        rows.extend(_state_row(rid, mask, coalesced[rid]) for rid in resource_ids)
    return rows


async def refresh_resource_states(
    session: AsyncSession, resource_ids: Collection[int]
) -> None:
    """Make the given resources' stored state match authoritative data.

    Runs in the caller's transaction, so it commits (or rolls back) with the
    write that triggered it. Resources that are no longer listable end up with
    no rows; ids that don't exist are ignored.
    """
    ids = sorted(set(resource_ids))
    if not ids:
        return
    await lock_resources(session, ids)
    await session.execute(
        delete(OGFieldResourceState).where(OGFieldResourceState.resource_id.in_(ids))
    )
    listable = list(
        (
            await session.scalars(resource_universe().where(ResourceModel.id.in_(ids)))
        ).all()
    )
    if listable:
        await session.execute(
            insert(OGFieldResourceState),
            await _compute_state_rows(session, sorted(listable)),
        )


async def refresh_resource_state(session: AsyncSession, resource_id: int) -> None:
    """``refresh_resource_states`` for a single resource."""
    await refresh_resource_states(session, [resource_id])


async def is_resource_state_ready(session: AsyncSession) -> bool:
    """True only when the last full rebuild completed; a missing row is not ready."""
    ready = await session.scalar(
        select(OGFieldResourceStateStatus.ready).where(
            OGFieldResourceStateStatus.key == RESOURCE_STATE_STATUS_KEY
        )
    )
    return ready is True


async def _set_ready(session: AsyncSession, ready: bool) -> None:
    status = await session.get(OGFieldResourceStateStatus, RESOURCE_STATE_STATUS_KEY)
    if status is None:
        status = OGFieldResourceStateStatus(key=RESOURCE_STATE_STATUS_KEY, ready=ready)
        session.add(status)
    status.ready = ready
    if ready:
        status.rebuilt_at = datetime.now(UTC)


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


@asynccontextmanager
async def _exclusive_rebuild(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    """Hold a Postgres advisory lock so only one full rebuild runs at a time.

    Uses a session-level lock on an autocommit connection, so it neither holds a
    transaction open for the whole rebuild nor conflicts with the status row the
    rebuild updates. No-op on other dialects.
    """
    async with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            yield
            return
        conn = await session.connection(
            execution_options={"isolation_level": "AUTOCOMMIT"}
        )
        acquired = await conn.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": _REBUILD_LOCK_KEY}
        )
        if not acquired:
            raise ResourceStateRebuildError(
                "Another resource-state rebuild is already running."
            )
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

    Each step commits on its own, so the table is never locked for the whole
    run. Readers stay on the live path throughout: readiness is cleared first and
    set again only after every batch commits and the integrity check passes. A
    failure leaves it cleared; leftover rows are invisible and overwritten by
    the next run. Write-path refreshes may run concurrently -- both sides lock a
    resource before recomputing it.
    """
    if batch_size < 1:
        raise ValueError(f"batch_size must be at least 1, got {batch_size}")

    async with _exclusive_rebuild(session_factory):
        async with session_factory.begin() as session:
            await _set_ready(session, False)
        async with session_factory.begin() as session:
            await session.execute(delete(OGFieldResourceState))
        async with session_factory() as session:
            ids = list(
                (
                    await session.scalars(
                        resource_universe().order_by(ResourceModel.id)
                    )
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
            if problems := await _integrity_problems(session):
                raise ResourceStateRebuildError(
                    "Resource-state rebuild failed its integrity check: "
                    + "; ".join(problems)
                )
            await _set_ready(session, True)
    return len(ids)
