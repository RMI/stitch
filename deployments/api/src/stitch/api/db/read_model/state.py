"""Build and maintain the ``og_field_resource_state`` current-state read model.

The read model is derived data: every row is the coalesced value of a resource for
one visibility profile (``permission_mask``). It is defined by the *same* live
coalescer the fallback read path uses (``utils.coalesce_resources``), restricted
to each mask's visible sources -- there is no second coalescing implementation, so
the cache cannot drift from live behavior.

Callers keep it current with the app-controlled hooks:

* ``refresh_resource_state`` / ``refresh_resource_states`` -- recompute one or many
  resources' rows (create/attach/reprioritize/merge). The steady-state mechanism:
  only the touched resources are rewritten.
* ``remove_resource_state`` -- drop a resource's rows (merged-away / repointed).
* ``refresh_changed_since`` -- recompute only resources whose inputs changed after a
  timestamp (targeted drift recovery).
* ``rebuild_all_resource_state`` -- full rebuild from scratch (bootstrap after the
  migration, or a coalescing-logic change). Proves the "rebuildable at any time"
  invariant; reserved for those cases since ongoing writes maintain rows in-band.

All run inside the caller's unit of work, so the cache commits atomically with the
data change that triggered it.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from datetime import datetime

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.ogsi.model import OGFieldResource

from ..model import (
    MembershipModel,
    OGFieldResourceAttributePriority,
    OGFieldResourceState,
)
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


async def _listable_ids(
    session: AsyncSession, resource_ids: Collection[int]
) -> list[int]:
    """Subset of ``resource_ids`` that would appear in a list (universe members).

    Uses the same universe definition as the list query so stored rows exactly
    match the set of listable resources.
    """
    if not resource_ids:
        return []
    universe = _resource_universe().subquery()
    rows = await session.scalars(
        select(universe.c.resource_id).where(
            universe.c.resource_id.in_(list(resource_ids))
        )
    )
    return list(rows.all())


async def remove_resource_state(session: AsyncSession, resource_id: int) -> None:
    """Delete a resource's read-model rows (e.g. after it is merged away)."""
    await session.execute(
        delete(OGFieldResourceState).where(
            OGFieldResourceState.resource_id == resource_id
        )
    )


async def refresh_resource_states(
    session: AsyncSession, resource_ids: Collection[int]
) -> None:
    """Recompute read-model rows for the given resources to match current data.

    Only these resources are touched: their rows are deleted, then the listable
    ones (non-repointed, active membership) get one row per permission mask.
    Non-listable resources are left with no rows, matching the list universe.
    """
    ids = list(dict.fromkeys(resource_ids))
    if not ids:
        return
    await session.execute(
        delete(OGFieldResourceState).where(OGFieldResourceState.resource_id.in_(ids))
    )
    listable = await _listable_ids(session, ids)
    if listable:
        session.add_all(await _compute_rows(session, listable))
    await session.flush()


async def refresh_resource_state(session: AsyncSession, resource_id: int) -> None:
    """Recompute a single resource's read-model rows (see ``refresh_resource_states``)."""
    await refresh_resource_states(session, [resource_id])


async def _resources_changed_since(session: AsyncSession, since: datetime) -> set[int]:
    """Resource ids whose coalescing inputs changed after ``since``.

    A resource's coalesced state changes only when its memberships or its
    per-attribute priorities change (values are only written alongside a new
    membership). Both tables carry an ``updated`` timestamp, so this captures
    attaches, merges (memberships flip), and re-prioritizations.
    """
    ids: set[int] = set()
    ids.update(
        (
            await session.scalars(
                select(MembershipModel.resource_id).where(
                    MembershipModel.updated > since
                )
            )
        ).all()
    )
    ids.update(
        (
            await session.scalars(
                select(OGFieldResourceAttributePriority.resource_id).where(
                    OGFieldResourceAttributePriority.updated > since
                )
            )
        ).all()
    )
    return ids


async def refresh_changed_since(
    session: AsyncSession, since: datetime
) -> Iterable[int]:
    """Recompute only resources whose inputs changed after ``since``; return their ids.

    Targeted drift recovery -- does not catch a coalescing-*logic* change (no input
    row is dirty then); use ``rebuild_all_resource_state`` for that.
    """
    ids = await _resources_changed_since(session, since)
    await refresh_resource_states(session, ids)
    return ids


async def rebuild_all_resource_state(session: AsyncSession) -> None:
    """Rebuild the entire read model from scratch (bootstrap / logic change).

    Wipes the table (``TRUNCATE`` on PostgreSQL to avoid dead-tuple churn) and
    recomputes every listable resource. Reserved for bootstrap and coalescing-logic
    changes; steady-state drift is handled incrementally by the refresh hooks.
    """
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        await session.execute(text("TRUNCATE TABLE og_field_resource_state"))
    else:
        await session.execute(delete(OGFieldResourceState))
    ids: Collection[int] = list((await session.scalars(_resource_universe())).all())
    if ids:
        session.add_all(await _compute_rows(session, list(ids)))
    await session.flush()
