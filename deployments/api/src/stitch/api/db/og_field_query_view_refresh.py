"""Write path for the EAV projection table ``og_field_resource_query_view``.

Rebuilds the precomputed projection from active memberships of non-repointed
resources. The unpivot must match the existing coalescing semantics exactly:
``value is None`` is the ONLY skip condition. Empty string ``""`` and empty
list ``[]`` are PRESENT and stored, preserving the empty-list-wins and
null-fall-through contracts the read path relies on.
"""

from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from stitch.ogsi.model.og_field import OilGasFieldBase

from .model import (
    MembershipModel,
    MembershipStatus,
    OGFieldResourceQueryView,
    OGFieldSourcePriority,
    OilGasFieldSourceModel,
    ResourceModel,
)
from .model.og_field_resource_query_view import FIELD_TO_VALUE_COLUMN


async def refresh_resources(
    session: AsyncSession, resource_ids: Collection[int]
) -> None:
    """Idempotent incremental refresh (delete + reinsert) for a set of resources."""
    if not resource_ids:
        return

    await session.execute(
        delete(OGFieldResourceQueryView).where(
            OGFieldResourceQueryView.resource_id.in_(resource_ids)
        )
    )

    # `priority` is denormalized into the projection at build time, so a change
    # to `og_field_source_priority` requires a `rebuild_all` to take effect.
    stmt = (
        select(
            MembershipModel.resource_id,
            MembershipModel.source,
            MembershipModel.source_pk,
            OGFieldSourcePriority.priority,
            OilGasFieldSourceModel,
        )
        .join(
            OilGasFieldSourceModel,
            OilGasFieldSourceModel.id == MembershipModel.source_pk,
        )
        .join(
            OGFieldSourcePriority,
            OGFieldSourcePriority.source == MembershipModel.source,
        )
        .join(ResourceModel, ResourceModel.id == MembershipModel.resource_id)
        .where(
            MembershipModel.resource_id.in_(resource_ids),
            MembershipModel.status == MembershipStatus.ACTIVE,
            ResourceModel.repointed_id.is_(None),
        )
    )

    rows: list[dict] = []
    for resource_id, source, source_pk, priority, source_model in await session.execute(
        stmt
    ):
        for field_name in OilGasFieldBase.model_fields:
            value = getattr(source_model, field_name)
            if value is None:
                continue  # None is the ONLY skip condition

            value_column = FIELD_TO_VALUE_COLUMN[field_name]
            if value_column == "value_num":
                stored = float(value)
            else:
                # value_text (string) and value_json (list) stored as-is;
                # "" and [] are present and must be persisted.
                stored = value

            rows.append(
                {
                    "resource_id": resource_id,
                    "source_id": source_pk,
                    "column_name": field_name,
                    "source": source,
                    "priority": priority,
                    value_column: stored,
                }
            )

    if rows:
        await session.execute(insert(OGFieldResourceQueryView), rows)

    await session.flush()


async def rebuild_all(session: AsyncSession, *, batch_size: int = 1000) -> None:
    """Full rebuild of the projection (used by stress script and backfill)."""
    await session.execute(delete(OGFieldResourceQueryView))

    resource_ids = (
        await session.scalars(
            select(ResourceModel.id).where(ResourceModel.repointed_id.is_(None))
        )
    ).all()

    for start in range(0, len(resource_ids), batch_size):
        await refresh_resources(session, resource_ids[start : start + batch_size])

    await session.flush()
