"""SQL-side coalescing over the long source-value representation.

For each ``(resource, colname)`` the highest-priority active source supplies the
value. Priority is ``COALESCE(per-resource override, default)``. Selection uses a
``ROW_NUMBER()`` window (portable to SQLite, unlike ``DISTINCT ON``); the winning
row carries its provenance (source + source_pk) for free.

Two consumers share the ``winners`` CTE:
  * the list endpoint pivots it back to one wide row per resource (in SQL);
  * the detail path streams winning rows and pivots in Python.
"""

from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import Text, and_, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.ogsi.model.og_field import OilGasFieldBase
from stitch.ogsi.model.types import OGSISrcKey

from .model import (
    MembershipModel,
    MembershipStatus,
    OGFieldResourceSourcePriority,
    OGFieldSourcePriority,
    OilGasFieldSourceModel,
    OilGasFieldSourceValueModel,
    ResourceModel,
)
from .model.oil_gas_field_source_value import (
    ATTRIBUTE_KINDS,
    ATTRIBUTE_NAMES,
    ValueKind,
    materialize_value,
    value_attr_for,
)

PROVENANCE_SUFFIX = "__provenance_source"


def build_coalesced_values(
    selected_sources: Collection[OGSISrcKey] | None = None,
    licensed_sources: Collection[OGSISrcKey] | None = None,
    resource_ids: Collection[int] | None = None,
):
    """CTE of the priority-winning value per (resource_id, colname).

    Columns: ``resource_id, colname, value_text, value_num, value_json,
    source, source_pk``.
    """
    s = OilGasFieldSourceModel
    v = OilGasFieldSourceValueModel
    m = MembershipModel
    r = ResourceModel
    p = OGFieldSourcePriority
    o = OGFieldResourceSourcePriority

    priority = func.coalesce(o.priority, p.priority)
    active_src = (
        select(
            r.id.label("resource_id"),
            m.source.label("source"),
            m.source_pk.label("source_pk"),
            priority.label("priority"),
        )
        .select_from(m)
        .join(r, r.id == m.resource_id)
        .join(p, p.source == m.source)
        .outerjoin(o, and_(o.resource_id == r.id, o.source == m.source))
        .where(
            r.repointed_id.is_(None),
            m.status == MembershipStatus.ACTIVE,
        )
    )
    if selected_sources is not None:
        active_src = active_src.where(
            m.source.in_(list(dict.fromkeys(selected_sources)))
        )
    if licensed_sources is not None:
        active_src = active_src.where(
            m.source.in_(list(dict.fromkeys(licensed_sources)))
        )
    if resource_ids is not None:
        active_src = active_src.where(r.id.in_(list(resource_ids)))
    # Join the source header on both pk AND source key: membership.source is not
    # FK-tied to the header's source, so matching only on source_pk could let a
    # mismatched membership row participate in coalescing.
    active_src = active_src.join(
        s, and_(s.id == m.source_pk, s.source == m.source)
    ).cte("active_src")

    ranked = (
        select(
            active_src.c.resource_id,
            active_src.c.source,
            active_src.c.source_pk,
            v.colname.label("colname"),
            v.value_text,
            v.value_num,
            v.value_json,
            func.row_number()
            .over(
                partition_by=(active_src.c.resource_id, v.colname),
                order_by=(active_src.c.priority.asc(), active_src.c.source.asc()),
            )
            .label("rn"),
        )
        .select_from(active_src)
        .join(v, v.source_pk == active_src.c.source_pk)
    ).cte("ranked")

    # rn == 1 keeps the single highest-priority row per (resource, colname).
    return select(ranked).where(ranked.c.rn == 1).cte("coalesced_values")


def _when_col(values_cte, field_name: str, value_col):
    """``value_col`` only on rows whose colname matches (NULL otherwise)."""
    return case((values_cte.c.colname == field_name, value_col))


def _pivot_value_column(values_cte, field_name: str):
    """The coalesced value for ``field_name`` as a labeled column.

    Exactly one row exists per (resource, colname), so MAX just selects that
    single non-null value. Postgres has no ``max(jsonb)`` aggregate, so JSON
    values are maxed as text; the caller (``_list_item_from_row``) deserializes
    those JSON-typed fields back to Python.
    """
    if ATTRIBUTE_KINDS[field_name] is ValueKind.JSON:
        return func.max(
            _when_col(values_cte, field_name, cast(values_cte.c.value_json, Text))
        ).label(field_name)
    value_col = getattr(values_cte.c, value_attr_for(field_name))
    return func.max(_when_col(values_cte, field_name, value_col)).label(field_name)


def _resource_spine(selected_sources: Collection[OGSISrcKey] | None):
    """Resources that should appear in the list (membership-based existence).

    Gated by the requested ``source`` filter but NOT by licensing: an
    unlicensed resource still appears, just with redacted (NULL) field values.
    """
    m = MembershipModel
    r = ResourceModel
    stmt = (
        select(r.id.label("id"))
        .select_from(r)
        .join(m, m.resource_id == r.id)
        .where(r.repointed_id.is_(None), m.status == MembershipStatus.ACTIVE)
    )
    if selected_sources is not None:
        stmt = stmt.where(m.source.in_(list(dict.fromkeys(selected_sources))))
    return stmt.distinct()


def build_resource_list_cte(
    selected_sources: Collection[OGSISrcKey] | None,
    licensed_sources: Collection[OGSISrcKey] | None,
):
    """One wide row per resource: ``id``, each field, each field+provenance.

    The resource spine (existence) is LEFT JOINed to the coalesced licensed
    values, so resources with only unlicensed/absent data appear with NULLs.
    """
    values_cte = build_coalesced_values(
        selected_sources=selected_sources, licensed_sources=licensed_sources
    )
    pivot = select(values_cte.c.resource_id.label("resource_id"))
    for field_name in ATTRIBUTE_NAMES:
        pivot = pivot.add_columns(
            _pivot_value_column(values_cte, field_name),
            func.max(_when_col(values_cte, field_name, values_cte.c.source)).label(
                f"{field_name}{PROVENANCE_SUFFIX}"
            ),
        )
    pivot = pivot.group_by(values_cte.c.resource_id).cte("resource_value_pivot")

    spine = _resource_spine(selected_sources).cte("resource_spine")
    coalesced = select(spine.c.id.label("id"))
    for field_name in ATTRIBUTE_NAMES:
        coalesced = coalesced.add_columns(
            pivot.c[field_name],
            pivot.c[f"{field_name}{PROVENANCE_SUFFIX}"],
        )
    coalesced = coalesced.select_from(
        spine.outerjoin(pivot, pivot.c.resource_id == spine.c.id)
    )
    return coalesced.cte("licensed_resource_list")


async def coalesce_persisted_resource(
    session: AsyncSession,
    resource_id: int,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> tuple[OilGasFieldBase, dict[str, tuple | None]]:
    """Coalesce a single persisted resource, pivoting the winning rows in Python."""
    values_cte = build_coalesced_values(
        selected_sources=None,
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
