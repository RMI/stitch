"""Maintenance of the single per-attribute priority store.

Every ``(resource, colname, source_pk)`` that has a value gets exactly one row in
``og_field_resource_attribute_priority``; coalescing then ranks by the single
``priority`` column. Two operations keep that table correct, both inside the
writing transaction:

* :func:`seed_or_refresh_defaults` -- (re)build the *default* rows for a resource
  from the global ``SOURCE_PRIORITY`` order, preserving any curated rows. Called on
  create / attach / merge.
* :func:`set_curated` -- replace one field's ordering, marking the listed sources
  curated (they take the low, winning positions) and re-deriving the rest as
  defaults. Called by the re-prioritize action.

Curated rows occupy the low priority positions and always outrank defaults, which
reproduces the previous two-tier (override-then-default) coalescing exactly.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.entities import User

from .model import (
    MembershipModel,
    MembershipStatus,
    OGFieldResourceAttributePriority,
    OilGasFieldSourceValueModel,
)
from .source_priority import source_priority_rank


async def _valued_members(
    session: AsyncSession, resource_id: int
) -> dict[str, dict[int, str]]:
    """``colname -> {source_pk: source_key}`` for every value the resource has.

    Drawn from the resource's ACTIVE memberships; license-agnostic (priority rows
    exist for every value, and licensing is applied only at read time).
    """
    m = MembershipModel
    v = OilGasFieldSourceValueModel
    rows = await session.execute(
        select(v.colname, m.source_pk, m.source)
        .select_from(m)
        .join(v, v.source_pk == m.source_pk)
        .where(
            m.resource_id == resource_id,
            m.status == MembershipStatus.ACTIVE,
        )
    )
    by_colname: dict[str, dict[int, str]] = {}
    for colname, source_pk, source in rows.all():
        by_colname.setdefault(colname, {})[source_pk] = source
    return by_colname


def _default_order(members: dict[int, str]) -> list[int]:
    """Source pks in global default order: SOURCE_PRIORITY rank, then source_pk."""
    return sorted(members, key=lambda pk: (source_priority_rank(members[pk]), pk))


async def seed_or_refresh_defaults(
    session: AsyncSession, user: User, resource_id: int
) -> None:
    """Rebuild the default priority rows for a resource, preserving curation.

    For each field the resource has a value for, curated rows are left untouched
    and the remaining valued sources are (re)written as default rows in global
    order, positioned after the curated block. Idempotent.
    """
    valued = await _valued_members(session, resource_id)

    existing = (
        await session.scalars(
            select(OGFieldResourceAttributePriority).where(
                OGFieldResourceAttributePriority.resource_id == resource_id
            )
        )
    ).all()
    curated_by_colname: dict[str, list[OGFieldResourceAttributePriority]] = {}
    for row in existing:
        if row.is_curated:
            curated_by_colname.setdefault(row.colname, []).append(row)

    for colname, members in valued.items():
        curated_rows = curated_by_colname.get(colname, [])
        curated_pks = {row.source_pk for row in curated_rows}
        # Defaults start after the highest curated position (which may be sparse
        # if a curated source's value was removed), so positions never collide.
        start = max((row.priority for row in curated_rows), default=-1) + 1

        # Replace only the default rows for this field; curated rows stay put.
        await session.execute(
            delete(OGFieldResourceAttributePriority).where(
                OGFieldResourceAttributePriority.resource_id == resource_id,
                OGFieldResourceAttributePriority.colname == colname,
                OGFieldResourceAttributePriority.is_curated.is_(False),
            )
        )
        default_pks = [pk for pk in _default_order(members) if pk not in curated_pks]
        session.add_all(
            OGFieldResourceAttributePriority.create(
                created_by=user,
                resource_id=resource_id,
                colname=colname,
                source=members[pk],
                source_pk=pk,
                priority=start + offset,
                is_curated=False,
            )
            for offset, pk in enumerate(default_pks)
        )
    await session.flush()


async def set_curated(
    session: AsyncSession,
    user: User,
    resource_id: int,
    colname: str,
    ordered_source_pks: Sequence[int],
) -> None:
    """Replace one field's ordering: ``ordered_source_pks`` become the curated tier.

    The listed sources take positions ``0..k-1`` (curated, winner-first); every
    other valued source for the field follows as a default in global order. Fully
    rewrites the field's rows for the resource.
    """
    members = (await _valued_members(session, resource_id)).get(colname, {})
    curated = list(ordered_source_pks)
    curated_set = set(curated)

    await session.execute(
        delete(OGFieldResourceAttributePriority).where(
            OGFieldResourceAttributePriority.resource_id == resource_id,
            OGFieldResourceAttributePriority.colname == colname,
        )
    )
    rows = [
        OGFieldResourceAttributePriority.create(
            created_by=user,
            resource_id=resource_id,
            colname=colname,
            source=members[pk],
            source_pk=pk,
            priority=position,
            is_curated=True,
        )
        for position, pk in enumerate(curated)
    ]
    defaults = [pk for pk in _default_order(members) if pk not in curated_set]
    rows.extend(
        OGFieldResourceAttributePriority.create(
            created_by=user,
            resource_id=resource_id,
            colname=colname,
            source=members[pk],
            source_pk=pk,
            priority=len(curated) + offset,
            is_curated=False,
        )
        for offset, pk in enumerate(defaults)
    )
    session.add_all(rows)
    await session.flush()
