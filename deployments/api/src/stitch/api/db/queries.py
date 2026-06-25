"""Pure construction of the source- and resource-list query/count statements.

Attribute values live in the long ``oil_gas_field_source_values`` table, not as
wide columns. The *source* path pivots each active-membership record's value rows
back into a wide, one-row-per-record CTE; the *resource* path first coalesces the
priority-winning value per ``(resource, colname)`` (``build_coalesced_values``)
and pivots that. Both narrow the pivot to only the attributes the current query
filters or sorts on, then build the filtered, sorted, paginated id-``Select`` the
endpoint needs. Construction is pure (no session); execution + hydration live in
``og_field_source_actions`` / ``og_field_resource_actions``.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any, Final

from sqlalchemy import (
    CTE,
    ColumnElement,
    Select,
    and_,
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
    OGFieldResourceSourcePriority,
    OGFieldSourcePriority,
    OilGasFieldSourceModel,
    OilGasFieldSourceValueModel,
    ResourceModel,
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


def _add_pivot_columns(stmt, fields, colname_col, value_col_for):
    """Add one ``max(case(colname == f, value))`` pivot column per field.

    Shared by the source and resource base builders. ``value_col_for(field)``
    returns the typed value column to pull (off the source value table or the
    coalesced CTE); ``colname_col`` is the colname column on the same row.
    """
    for field_name in fields:
        stmt = stmt.add_columns(
            func.max(
                case((colname_col == field_name, value_col_for(field_name)))
            ).label(field_name)
        )
    return stmt


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

    stmt = _add_pivot_columns(
        stmt,
        _participating_columns(params),
        v.colname,
        lambda field_name: getattr(v, value_attr_for(field_name)),
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


def _build_field_conditions(
    cte: CTE,
    params: OGFieldQueryParams,
) -> list[ColumnElement[bool]]:
    """Path-agnostic q-ILIKE + exact-match filters over the pivoted columns.

    Shared by the source and resource paths: every condition references a
    pivoted/header column via ``_require_column`` so a narrowing drift raises
    rather than silently dropping a filter. Source-membership filters
    (``source`` / ``licensed_sources``) are appended by the source path's
    ``_build_conditions``; the resource path does not post-filter by source.
    """
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

    return conditions


def _build_conditions(
    cte: CTE,
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> list[ColumnElement[bool]]:
    conditions = _build_field_conditions(cte, params)

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


def _id_select(base, conditions, params=None, sort_clauses=None):
    """``select(base.c.id)`` + WHEREs, optionally ordered + paginated.

    With ``sort_clauses`` (query path) the result is ordered then sliced by
    ``params.offset``/``params.limit``; without it (count path) the filtered,
    unordered, unpaginated select the caller wraps in ``count()``.
    """
    stmt = select(base.c.id)
    for cond in conditions:
        stmt = stmt.where(cond)
    if sort_clauses is not None:
        stmt = stmt.order_by(*sort_clauses).offset(params.offset).limit(params.limit)
    return stmt


def construct_sources_query_statement(
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> Select[tuple[int]]:
    """Filtered + sorted + paginated id-``Select`` for the source-list query."""
    base = base_source_query_statement(params, licensed_sources=licensed_sources)
    return _id_select(
        base,
        _build_conditions(base, params, licensed_sources),
        params=params,
        sort_clauses=_build_sort_clauses(base, params),
    )


def construct_sources_count_statement(
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> Select[tuple[int]]:
    """Filtered (unordered, unpaginated) id-``Select``; caller wraps in count()."""
    base = base_source_query_statement(params, licensed_sources=licensed_sources)
    return _id_select(base, _build_conditions(base, params, licensed_sources))


# --------------------------------------------------------------------------- #
# Resource path: live coalescing + the two-phase ids -> hydrate flow.
# --------------------------------------------------------------------------- #


def build_coalesced_values(
    licensed_sources: Collection[OGSISrcKey] | None = None,
    resource_ids: Collection[int] | None = None,
    colnames: Collection[str] | None = None,
) -> CTE:
    """CTE of the priority-winning value per ``(resource_id, colname)``.

    Columns: ``resource_id, colname, value_text, value_num, value_json,
    source, source_pk``. Priority is ``COALESCE(per-resource override, default)``;
    the winner is the ``rn == 1`` row of a ``ROW_NUMBER()`` window ordered by
    priority then source then source_pk (portable to SQLite, unlike
    ``DISTINCT ON``). ``licensed_sources`` filters ``active_src`` *before* the
    window, so an unlicensed higher-priority source falls through to the next
    licensed one. ``colnames`` narrows the windowed pass to just those fields;
    ``resource_ids`` narrows it to those resources.
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

    ranked_select = (
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
                # source_pk is the final tie-break so the winner is deterministic
                # even when a resource has multiple records of the same source
                # (same priority + same source key).
                order_by=(
                    active_src.c.priority.asc(),
                    active_src.c.source.asc(),
                    active_src.c.source_pk.asc(),
                ),
            )
            .label("rn"),
        )
        .select_from(active_src)
        .join(v, v.source_pk == active_src.c.source_pk)
    )
    if colnames is not None:
        ranked_select = ranked_select.where(
            v.colname.in_(list(dict.fromkeys(colnames)))
        )
    ranked = ranked_select.cte("ranked")

    # rn == 1 keeps the single highest-priority row per (resource, colname).
    return select(ranked).where(ranked.c.rn == 1).cte("coalesced_values")


def _resource_universe() -> Select:
    """Resources that should appear in the list (membership-derived existence).

    ``DISTINCT resource_id`` for non-repointed resources with an ACTIVE
    membership. NOT gated by ``source`` or licensing: a resource whose only
    source has all-null attributes (zero coalesced rows) still appears as a
    null-shell, and an unlicensed resource appears with redacted (NULL) values.
    """
    m = MembershipModel
    r = ResourceModel
    return (
        select(r.id.label("id"))
        .select_from(r)
        .join(m, m.resource_id == r.id)
        .where(r.repointed_id.is_(None), m.status == MembershipStatus.ACTIVE)
        .distinct()
    )


def base_resource_query_statement(
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> CTE:
    """One row per resource in the universe, narrowed to ``params``.

    The membership-derived universe is LEFT JOINed to a single GROUP BY pivot of
    the coalesced licensed values over only the participating fields, so the full
    wide pivot is never computed here. Exposes ``id`` (the resource id) plus each
    participating field. JSON attributes (owners/operators) are never filterable
    or sortable -- the closed Literal param types keep them out of the
    participating set -- so there is no JSON branch (and no ``max(jsonb)``); when
    no field participates there is no pivot at all.
    """
    involved = _participating_columns(params)
    universe = _resource_universe().cte("resource_universe")

    if not involved:
        return select(universe.c.id.label("id")).cte("resource_base")

    values_cte = build_coalesced_values(
        licensed_sources=licensed_sources, colnames=involved
    )
    pivot = _add_pivot_columns(
        select(values_cte.c.resource_id.label("resource_id")),
        involved,
        values_cte.c.colname,
        lambda field_name: getattr(values_cte.c, value_attr_for(field_name)),
    )
    pivot = pivot.group_by(values_cte.c.resource_id).cte("resource_value_pivot")

    stmt = select(universe.c.id.label("id"))
    for field_name in involved:
        stmt = stmt.add_columns(pivot.c[field_name])
    stmt = stmt.select_from(
        universe.outerjoin(pivot, pivot.c.resource_id == universe.c.id)
    )
    return stmt.cte("resource_base")


def _build_resource_sort_clauses(cte: CTE, params: OGFieldQueryParams) -> list[Any]:
    direction = desc if params.sort_order == "desc" else asc

    # On resources, id and resource_id both name the resource id: a real id-sort
    # honoring direction (not a degrade to the tiebreak as on the source path).
    if params.sort_by in {"id", "resource_id"}:
        return [direction(cte.c.id).nulls_last()]

    return [
        direction(_require_column(cte, params.sort_by)).nulls_last(),
        asc(cte.c.id),
    ]


def construct_resources_query_statement(
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> Select[tuple[int]]:
    """Filtered + sorted + paginated id-``Select`` for the resource-list query."""
    base = base_resource_query_statement(params, licensed_sources=licensed_sources)
    return _id_select(
        base,
        _build_field_conditions(base, params),
        params=params,
        sort_clauses=_build_resource_sort_clauses(base, params),
    )


def construct_resources_count_statement(
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> Select[tuple[int]]:
    """Filtered (unordered, unpaginated) id-``Select``; caller wraps in count()."""
    base = base_resource_query_statement(params, licensed_sources=licensed_sources)
    return _id_select(base, _build_field_conditions(base, params))
