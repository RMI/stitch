"""Pure construction of the source-record query/count statements.

A source record's attributes live in the long ``oil_gas_field_source_values``
table, not as wide columns. These helpers pivot each active-membership record's
value rows back into a wide, one-row-per-record CTE -- narrowed to only the
attributes the current query filters or sorts on -- then build the filtered,
sorted, paginated id-``Select`` the endpoint needs. Construction is pure (no
session); execution + hydration live in ``og_field_source_actions``.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any, Final

from sqlalchemy import (
    CTE,
    ColumnElement,
    Select,
    asc,
    case,
    desc,
    func,
    or_,
    select,
)

from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    OilGasFieldSourceModel,
    OilGasFieldSourceValueModel,
)
from stitch.api.db.model.oil_gas_field_source_value import value_attr_for
from stitch.api.entities import OGSI_SOURCE_DEFAULT, OGFieldQueryParams
from stitch.ogsi.model.types import OGSISrcKey

# Single source of truth for the source-list field metadata. This is a shared
# cross-module contract: the resource-list actions import these constants too.
Q_FIELDS: Final[tuple[str, ...]] = (
    "name",
    "name_local",
    "basin",
    "state_province",
    "region",
)

EXACT_MATCH_FIELDS: Final[tuple[str, ...]] = (
    *Q_FIELDS,
    "id",
    "country",
    "field_status",
    "location_type",
    "production_conventionality",
    "primary_hydrocarbon_group",
)

PRIMARY_SORT_COL: Final[str] = "id"

# Sort targets resolved from a header column (``id``/``source``) or absent on
# the source path (``resource_id``); none of these need a pivoted value column.
_HEADER_SORT_FIELDS: Final[frozenset[str]] = frozenset({"id", "source", "resource_id"})


def _participating_columns(params: OGFieldQueryParams) -> list[str]:
    """Value attributes the query actually touches -- the columns to pivot.

    The sort field (unless it resolves from a header column), every *set*
    exact-match field, and ``Q_FIELDS`` when a substring search is requested.
    ``id`` is excluded: it is a header column on the base select, not pivoted.
    Order is preserved and duplicates removed.
    """
    participating: list[str] = []
    if params.sort_by not in _HEADER_SORT_FIELDS:
        participating.append(params.sort_by)

    for field in EXACT_MATCH_FIELDS:
        if field != "id" and getattr(params, field, None) is not None:
            participating.append(field)

    if params.q:
        participating += Q_FIELDS

    return list(dict.fromkeys(participating))


def base_source_query_statement(
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> CTE:
    """One wide row per active-membership source record, narrowed to ``params``.

    ``id``/``source`` come straight off the header; each participating value
    attribute is pivoted out of its typed value column. JSON attributes
    (owners/operators) are never filterable or sortable -- the closed Literal
    param types keep them out of the participating set -- so no JSON branch is
    needed here (this also sidesteps the missing ``max(jsonb)`` aggregate).
    """
    s = OilGasFieldSourceModel
    m = MembershipModel
    v = OilGasFieldSourceValueModel

    # EXISTS rather than a join to memberships: a record can have several
    # memberships, and a join would fan it out to one row per membership,
    # inflating the GROUP BY pivot. Correlate on both pk AND source key
    # (membership.source is not FK-tied to the header's source) so a mismatched
    # row cannot mark the record active.
    active_membership = (
        select(1)
        .where(m.source_pk == s.id)
        .where(m.source == s.source)
        .where(m.status == MembershipStatus.ACTIVE)
        .exists()
    )

    stmt = (
        select(s.id.label("id"), s.source.label("source"))
        .select_from(s)
        .outerjoin(v, v.source_pk == s.id)
        .where(active_membership)
    )
    if licensed_sources is not None:
        stmt = stmt.where(s.source.in_(list(dict.fromkeys(licensed_sources))))
    stmt = stmt.group_by(s.id, s.source)

    for field_name in _participating_columns(params):
        value_col = getattr(v, value_attr_for(field_name))
        stmt = stmt.add_columns(
            func.max(case((v.colname == field_name, value_col))).label(field_name)
        )
    return stmt.cte("source_base")


def _require_column(cte: CTE, field_name: str) -> ColumnElement[Any]:
    """Return ``cte.c.<field_name>`` or raise if the narrowing dropped it.

    Conditions and sort clauses are derived from the same
    ``_participating_columns`` result as the pivot, so a missing column means
    the narrowing drifted -- raise (per the repo convention) rather than
    silently drop the filter/sort, which would return wrong rows.
    """
    col = getattr(cte.c, field_name, None)
    if col is None:
        raise RuntimeError(
            f"source query references {field_name!r}, absent from the narrowed "
            "pivot; participating-columns narrowing is out of sync."
        )
    return col


def _build_conditions(
    cte: CTE,
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []

    if params.q:
        q_term = f"%{params.q}%"
        conditions.append(
            or_(*(_require_column(cte, field).ilike(q_term) for field in Q_FIELDS))
        )

    for field_name in EXACT_MATCH_FIELDS:
        value = getattr(params, field_name, None)
        if value is None:
            continue
        conditions.append(_require_column(cte, field_name) == value)

    sources = list(dict.fromkeys(getattr(params, "source", OGSI_SOURCE_DEFAULT)))
    conditions.append(cte.c.source.in_(sources))
    if licensed_sources is not None:
        conditions.append(cte.c.source.in_(list(dict.fromkeys(licensed_sources))))

    return conditions


def _build_sort_clauses(cte: CTE, params: OGFieldQueryParams) -> list[Any]:
    clauses: list[Any] = []

    # resource_id does not exist on the source path; a sort by it degrades to
    # the id tiebreak below (matching the prior mixin behavior).
    if params.sort_by != "resource_id":
        sort_col = _require_column(cte, params.sort_by)
        direction = desc if params.sort_order == "desc" else asc
        clauses.append(direction(sort_col).nulls_last())

    if params.sort_by != PRIMARY_SORT_COL:
        clauses.append(asc(_require_column(cte, PRIMARY_SORT_COL)))

    return clauses


def construct_sources_query_statement(
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> Select[tuple[int]]:
    """Filtered + sorted + paginated id-``Select`` for the source-list query."""
    base = base_source_query_statement(params, licensed_sources=licensed_sources)
    stmt = select(base.c.id)
    for cond in _build_conditions(base, params, licensed_sources):
        stmt = stmt.where(cond)
    stmt = stmt.order_by(*_build_sort_clauses(base, params))
    return stmt.offset(params.offset).limit(params.limit)


def construct_sources_count_statement(
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> Select[tuple[int]]:
    """Filtered (unordered, unpaginated) id-``Select``; caller wraps in count()."""
    base = base_source_query_statement(params, licensed_sources=licensed_sources)
    stmt = select(base.c.id)
    for cond in _build_conditions(base, params, licensed_sources):
        stmt = stmt.where(cond)
    return stmt
