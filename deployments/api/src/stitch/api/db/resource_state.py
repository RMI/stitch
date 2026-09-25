"""Maintenance of the precomputed ``og_field_resource_state`` table.

The table is derived data (see ``model.og_field_resource_state``): it caches the
ranked coalescing candidates the ``list`` / ``filter-options`` read paths consume.
It is kept in sync by recomputing the affected resources in-transaction from the
write paths that change coalesced output (attach source, reprioritize, merge).

``refresh_resource_state`` is a delete-then-insert for a set of resource ids,
built entirely from ``queries.resource_state_rows`` so the stored ranking can
never drift from the live query. Refreshing a now-repointed id inserts no rows
(the ranking query excludes repointed resources), which doubles as the delete a
merge needs.
"""

from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.observability.context import named_query

from .model import OGFieldResourceStateModel, ResourceModel
from .queries import resource_state_rows


async def refresh_resource_state(
    session: AsyncSession, resource_ids: Collection[int]
) -> None:
    """Recompute ``og_field_resource_state`` rows for ``resource_ids``.

    Deletes the existing rows for those resources and re-inserts the freshly
    ranked, truncated candidates. A no-op for an empty ``resource_ids``. Flushes
    but does not commit -- callers run this inside their own transaction.
    """
    ids = list(dict.fromkeys(resource_ids))
    if not ids:
        return
    with named_query("resources.state.refresh"):
        await session.execute(
            delete(OGFieldResourceStateModel).where(
                OGFieldResourceStateModel.resource_id.in_(ids)
            )
        )
        rows = resource_state_rows(resource_ids=ids)
        await session.execute(
            insert(OGFieldResourceStateModel).from_select(
                [
                    "resource_id",
                    "colname",
                    "rank",
                    "source",
                    "source_pk",
                    "value_text",
                    "value_num",
                    "value_json",
                ],
                rows,
            )
        )
        await session.flush()


async def rebuild_all_resource_state(session: AsyncSession) -> None:
    """Rebuild the entire ``og_field_resource_state`` table from scratch.

    Truncates the table and repopulates it for every root (non-repointed)
    resource. Used by the initial migration backfill, the seed tooling, and tests.
    """
    with named_query("resources.state.rebuild"):
        await session.execute(delete(OGFieldResourceStateModel))
        root_ids = (
            await session.scalars(
                select(ResourceModel.id).where(ResourceModel.repointed_id.is_(None))
            )
        ).all()
    await refresh_resource_state(session, root_ids)
