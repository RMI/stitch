"""Detail-path executor over the SQL-side coalescing core.

The coalescing primitive (``build_coalesced_values``) now lives in ``queries.py``
as the shared foundation for both the source and resource list paths. This module
keeps the single-resource detail path: stream the winning rows for one resource
and pivot them in Python, carrying provenance (value, source, source_pk).
"""

from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.ogsi.model.og_field import OilGasFieldBase
from stitch.ogsi.model.types import OGSISrcKey

from .model.oil_gas_field_source_value import ATTRIBUTE_NAMES, materialize_value
from .queries import build_coalesced_values


async def coalesce_persisted_resource(
    session: AsyncSession,
    resource_id: int,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> tuple[OilGasFieldBase, dict[str, tuple | None]]:
    """Coalesce a single persisted resource, pivoting the winning rows in Python."""
    values_cte = build_coalesced_values(
        licensed_sources=licensed_sources,
        resource_ids=[resource_id],
    )
    stmt = select(
        values_cte.c.colname,
        values_cte.c.value_text,
        values_cte.c.value_num,
        values_cte.c.value_json,
        values_cte.c.source,
        values_cte.c.source_pk,
    )
    rows = (await session.execute(stmt)).mappings().all()

    view_data: dict[str, object] = {k: None for k in ATTRIBUTE_NAMES}
    provenance: dict[str, tuple | None] = {k: None for k in ATTRIBUTE_NAMES}
    for row in rows:
        colname = row["colname"]
        value = materialize_value(
            colname,
            value_text=row["value_text"],
            value_num=row["value_num"],
            value_json=row["value_json"],
        )
        view_data[colname] = value
        provenance[colname] = (value, row["source"], row["source_pk"])

    return OilGasFieldBase(**view_data), provenance
