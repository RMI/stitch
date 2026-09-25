"""Build and maintain the ``og_field_resource_state`` current-state read model.

The read model is derived data: every row is the coalesced value of a resource for
one visibility profile (``permission_mask``). It is defined by the *same* live
coalescer the fallback read path uses (``utils.coalesce_resources``), restricted
to each mask's visible sources -- there is no second coalescing implementation, so
the cache cannot drift from live behavior.

Callers keep it current with the app-controlled hooks:

* ``refresh_resource_state`` -- recompute one resource's rows (create/attach/reprioritize).
* ``remove_resource_state``  -- drop a resource's rows (merged-away / repointed).
* ``rebuild_all_resource_state`` -- full rebuild from scratch (migration backfill,
  maintenance). Proves the "rebuildable at any time" invariant.

All run inside the caller's unit of work, so the cache commits atomically with the
data change that triggered it.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.ogsi.model import OGFieldResource

from ..model import OGFieldResourceState
from ..model.oil_gas_field_source_value import ATTRIBUTE_NAMES
from ..queries import _resource_universe
from ..utils import coalesce_resources
from .permissions import ALL_MASKS, visible_sources_for_mask


def _state_row(
    resource_id: int, mask: int, resource: OGFieldResource
) -> OGFieldResourceState:
    """One read-model row from an already-coalesced resource entity."""
    view = resource.view
    data = {} if view is None else view.model_dump(mode="json")
    provenance = {
        field: (None if prov is None else prov[1])
        for field, prov in resource.provenance.items()
    }
    return OGFieldResourceState(
        resource_id=resource_id,
        permission_mask=mask,
        provenance=provenance,
        **{field: data.get(field) for field in ATTRIBUTE_NAMES},
    )


async def _compute_rows(
    session: AsyncSession, resource_ids: Sequence[int]
) -> list[OGFieldResourceState]:
    """Coalesced rows for every ``(resource, mask)`` pair, one coalesce per mask."""
    rows: list[OGFieldResourceState] = []
    for mask in ALL_MASKS:
        visible = visible_sources_for_mask(mask)
        coalesced = await coalesce_resources(session, resource_ids, visible)
        rows.extend(_state_row(rid, mask, coalesced[rid]) for rid in resource_ids)
    return rows


async def _is_listable(session: AsyncSession, resource_id: int) -> bool:
    """True when the resource would appear in a list (non-repointed, active member).

    Uses the same universe definition as the list query so stored rows exactly
    match the set of listable resources.
    """
    universe = _resource_universe().subquery()
    found = await session.scalar(
        select(universe.c.resource_id)
        .where(universe.c.resource_id == resource_id)
        .limit(1)
    )
    return found is not None


async def remove_resource_state(session: AsyncSession, resource_id: int) -> None:
    """Delete a resource's read-model rows (e.g. after it is merged away)."""
    await session.execute(
        delete(OGFieldResourceState).where(
            OGFieldResourceState.resource_id == resource_id
        )
    )


async def refresh_resource_state(session: AsyncSession, resource_id: int) -> None:
    """Recompute one resource's read-model rows to match current data.

    Deletes any existing rows and, when the resource is listable, reinserts one
    row per permission mask. A non-listable resource (repointed, or with no active
    membership) is left with no rows, matching the list universe.
    """
    await remove_resource_state(session, resource_id)
    if not await _is_listable(session, resource_id):
        return
    session.add_all(await _compute_rows(session, [resource_id]))
    await session.flush()


async def rebuild_all_resource_state(session: AsyncSession) -> None:
    """Rebuild the entire read model from scratch (data source of truth)."""
    await session.execute(delete(OGFieldResourceState))
    ids: Collection[int] = list((await session.scalars(_resource_universe())).all())
    if ids:
        session.add_all(await _compute_rows(session, list(ids)))
    await session.flush()
