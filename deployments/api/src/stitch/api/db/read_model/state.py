"""Build and maintain ``og_field_resource_state`` from the coalescer.

Every stored row comes from ``queries.coalesced_winner_rows`` -- the same SQL
ranking the detail view coalesces with -- run once per permission profile with
that profile's exact source set. There is no second ranking implementation, so
stored state can't drift from how a resource coalesces. Values are materialized
the same way the detail view materializes them and are not validated here: like
any read, a list page validates the rows it shows, so a stored value today's
model rejects can't stop a rebuild or a write.

* ``refresh_resource_states`` recomputes the given resources inside the caller's
  transaction: lock their rows, delete their state, and re-insert one row per
  profile for those still listable. A resource that stopped being listable (e.g.
  merged away) is left with no rows.
* ``rebuild_all_resource_state`` recomputes every listable resource in committed
  batches, then removes rows of resources that are no longer listable. It never
  empties the table: each batch replaces only its own resources' rows, so a
  reader mid-rebuild finds a complete row for every resource.
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from typing import Any, Final

from sqlalchemy import Select, delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.api.observability.context import named_query

from ..model import OGFieldResourceState, ResourceModel
from ..model.oil_gas_field_source_value import ATTRIBUTE_NAMES, materialize_value
from ..queries import coalesced_winner_rows, resource_universe
from .permissions import PERMISSION_MASKS, visible_sources_for_mask

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE: Final[int] = 500


def lock_resources_statement(resource_ids: Collection[int]) -> Select[tuple[int]]:
    """``SELECT ... FOR NO KEY UPDATE`` over the resource rows, in ascending id
    order.

    A stable order means two transactions locking overlapping sets (e.g. two
    merges) always queue in the same order instead of deadlocking.
    """
    return (
        select(ResourceModel.id)
        .where(ResourceModel.id.in_(sorted(set(resource_ids))))
        .order_by(ResourceModel.id)
        .with_for_update(key_share=True)
    )


async def lock_resources(session: AsyncSession, resource_ids: Collection[int]) -> None:
    """Lock the resource rows until the caller's transaction ends.

    ``FOR NO KEY UPDATE`` is the lock Postgres already takes to update a
    resource's non-key columns (e.g. a merge setting ``repointed_id``). It
    conflicts with itself, so concurrent writers to a resource queue, but not
    with the key-share lock that inserting any row referencing a resource takes
    (a membership, a merge candidate's items, ...). ``FOR UPDATE`` would conflict
    with those: a transaction holding one resource and waiting on a second,
    while an insert holds a key-share lock on the second and waits on the first,
    deadlock.

    Write actions take it at their start, before their own reads: the second of
    two concurrent writers waits, then reads the first's committed changes --
    including a merge that repointed the resource -- so neither acts on stale
    data or overwrites the other with a stale recompute.
    ``refresh_resource_states`` locks again (a no-op when already held) to
    protect callers like the full rebuild. SQLite has no row locks (it already
    serializes writers), so this is a no-op there.
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

    Each winner's value is materialized and its source key recorded as
    provenance. Fields with no winner stay unset.
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


async def _delete_unlistable_state(session: AsyncSession) -> None:
    """Drop rows of resources that are no longer listable (e.g. merged away)."""
    universe = resource_universe().subquery()
    await session.execute(
        delete(OGFieldResourceState).where(
            OGFieldResourceState.resource_id.not_in(select(universe.c.resource_id))
        )
    )


async def rebuild_all_resource_state(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Recompute every listable resource's state; return how many were rebuilt.

    Each batch commits on its own and locks only its own resources, so the API
    keeps serving throughout: reads never wait, and a write waits at most for
    the batch holding its resource. Rows of resources that are no longer
    listable are removed at the end. A failed run leaves every batch it
    finished in place; running it again finishes the job.
    """
    if batch_size < 1:
        raise ValueError(f"batch_size must be at least 1, got {batch_size}")

    async with session_factory() as session:
        pending = list(
            (
                await session.scalars(resource_universe().order_by(ResourceModel.id))
            ).all()
        )
    for start in range(0, len(pending), batch_size):
        async with session_factory.begin() as session:
            await refresh_resource_states(session, pending[start : start + batch_size])
        logger.info(
            "Rebuilt resource state for %d of %d resources.",
            min(start + batch_size, len(pending)),
            len(pending),
        )
    async with session_factory.begin() as session:
        await _delete_unlistable_state(session)
    return len(pending)
