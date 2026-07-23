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

from collections.abc import Callable, Collection
from typing import Any, Final, Literal

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
from stitch.api.entities import OGFieldQueryParams
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
    "country",
    "field_status",
    "location_type",
    "production_conventionality",
    "primary_hydrocarbon_group",
)

# Sort targets resolved from a header/identity column rather than a pivoted value
# column: ``id``/``resource_id`` map to the path's own id, ``source`` to the
# source key. None of these need a pivoted value column.
_HEADER_SORT_FIELDS: Final[frozenset[str]] = frozenset({"id", "source", "resource_id"})


def _participating_columns(params: OGFieldQueryParams) -> list[str]:
    """Value attributes the query actually touches -- the columns to pivot.

    The sort field (unless it resolves from a header column), every *set*
    exact-match field, and ``Q_FIELDS`` when a substring search is requested.
    Identity columns (``id``) are never here: they are filtered/sorted against
    the path's own id column, not pivoted. Order is preserved, duplicates removed.
    """
    participating: list[str] = []
    if params.sort_by not in _HEADER_SORT_FIELDS:
        participating.append(params.sort_by)

    for field in EXACT_MATCH_FIELDS:
        if getattr(params, field, None) is not None:
            participating.append(field)

    if params.q:
        participating += Q_FIELDS

    return list(dict.fromkeys(participating))


def construct_base_query_statement(
    licensed_sources: Collection[OGSISrcKey] | None = None,
    resource_ids: Collection[int] | None = None,
) -> CTE:
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
            v.colname.label("colname"),
            v.value_text,
            v.value_num,
            v.value_json,
        )
        .select_from(m)
        .join(r, r.id == m.resource_id)
        .join(p, p.source == m.source)
        .join(s, and_(s.id == m.source_pk, s.source == m.source))
        .join(v, v.source_pk == m.source_pk)
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
    # Narrow to specific resources before ranking so the window partitions cover
    # only those resources -- a detail/page hydration must not rank every active
    # row in the table.
    if resource_ids is not None:
        active_src = active_src.where(
            m.resource_id.in_(list(dict.fromkeys(resource_ids)))
        )
    return active_src.cte("active_src")


def base_source_query(
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> Select[tuple[int]]:
    involved = _participating_columns(params)
    base_cte = construct_base_query_statement(licensed_sources)
    pivot = select(base_cte.c.source_pk, base_cte.c.source).group_by(
        base_cte.c.source_pk, base_cte.c.source
    )
    pivot = _add_pivot_columns(
        pivot,
        involved,
        base_cte.c.colname,
        lambda fn: getattr(base_cte.c, value_attr_for(fn)),
    )
    pivot_cte = pivot.cte("source_base")
    stmt = select(pivot_cte.c.source_pk)
    for cond in _build_field_conditions(pivot_cte, params):
        stmt = stmt.where(cond)
    # source is a source-path-only filter; the resource universe is source-ignoring.
    stmt = stmt.where(pivot_cte.c.source.in_(list(dict.fromkeys(params.source))))
    if params.id is not None:
        stmt = stmt.where(pivot_cte.c.source_pk == params.id)
    return stmt.order_by(*_build_sort_clauses(pivot_cte, params, "source_pk"))


def _ranked(base_cte: CTE) -> CTE:
    """Attach the coalesce rank ``rn`` to every candidate row (no winner cut).

    The single definition of the coalescing order, shared by the winner cut
    (``add_ranking`` -> ``rn == 1``) and the all-candidates detail hydration
    (``coalesced_candidate_rows``) so the two can't drift. ``rn == 1`` is the
    winner within each ``(resource_id, colname)`` partition.

    MERGE(174): 174 introduces this same ``_ranked`` split, but with tiered
    per-field override ranking (``override_priority`` NULLS LAST, then
    ``default_priority``, then source/source_pk). On merge keep 174's richer
    ``order_by`` -- this branch differs there only because per-field overrides
    don't exist here yet. BUT drop 174's ``.where(value_text != "")`` empty-text
    filter: this branch makes empty strings impossible at write time + a DB
    CHECK (see ``model.oil_gas_field_source_value``), so that filter is now dead.
    """
    cols = base_cte.c
    return (
        select(base_cte)
        .add_columns(
            func.row_number()
            .over(
                partition_by=(cols.resource_id, cols.colname),
                order_by=(
                    cols.priority.asc(),
                    cols.source.asc(),
                    cols.source_pk.asc(),
                ),
            )
            .label("rn")
        )
        .cte()
    )


def add_ranking(base_cte: CTE) -> Select[tuple[Any, ...]]:
    ranked = _ranked(base_cte)
    return select(ranked).where(ranked.c.rn == 1)


def coalesced_winner_rows(
    resource_ids: Collection[int],
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> Select[tuple[Any, ...]]:
    """Winning ``(value, source)`` per ``(resource, field)`` for given resources.

    One row per ``(resource_id, colname)`` that wins coalescing -- the same
    priority ranking the list/filter path uses (``add_ranking``). The base CTE is
    narrowed to ``resource_ids`` *before* ranking, so the window partitions cover
    only the requested resources rather than the whole table. Callers materialize
    the typed value and read the winning ``source``/``source_pk`` as provenance;
    the winner is already chosen in SQL, so no priority logic remains in Python.
    """
    base = construct_base_query_statement(licensed_sources, resource_ids=resource_ids)
    winners = add_ranking(base).cte("coalesced_winners")
    return select(
        winners.c.resource_id,
        winners.c.colname,
        winners.c.value_text,
        winners.c.value_num,
        winners.c.value_json,
        winners.c.source,
        winners.c.source_pk,
    )


def coalesced_candidate_rows(
    resource_ids: Collection[int],
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> Select[tuple[Any, ...]]:
    """Every ranked candidate value row for the given resources, winner-first.

    ``coalesced_winner_rows`` *without* the ``rn == 1`` cut: it keeps all
    candidate rows (each tagged with ``rn``) and joins each source header for
    ``source_record``. This lets the detail path build both the coalesced view +
    provenance (the ``rn == 1`` rows) and the raw ``source_data`` (all rows,
    grouped by ``source_pk``) from a SINGLE query, replacing the former
    winner-query + ``source_data_by_resource_id`` pair (see
    ``utils.resource_model_to_entity``). Rows are ordered
    ``(priority, source, source_pk, colname)`` so grouping by source yields
    sources best-priority-first, matching the old source ordering.

    ``source_record`` repeats per value row -- bounded (one resource's handful of
    sources), needed to rebuild the source entities, and dropped again by the
    source *view*.

    MERGE(174): rides on 174's tiered ``_ranked`` unchanged. If the lazy
    field-source endpoint is later folded into the detail payload, this is the
    query it would build on.
    """
    base = construct_base_query_statement(licensed_sources, resource_ids=resource_ids)
    ranked = _ranked(base)
    s = OilGasFieldSourceModel
    return (
        select(
            ranked.c.resource_id,
            ranked.c.colname,
            ranked.c.value_text,
            ranked.c.value_num,
            ranked.c.value_json,
            ranked.c.source,
            ranked.c.source_pk,
            ranked.c.rn,
            s.source_record,
        )
        .join(s, s.id == ranked.c.source_pk)
        .order_by(
            ranked.c.priority,
            ranked.c.source,
            ranked.c.source_pk,
            ranked.c.colname,
        )
    )


def _resource_universe() -> Select[tuple[int]]:
    """Resources eligible to appear in a list: any non-repointed resource with an
    active membership. Membership-derived and ungated by licensing/source, so a
    resource whose licensed values are all absent still appears as a null-shell on
    an unfiltered list (and drops out once a field is filtered)."""
    m = MembershipModel
    r = ResourceModel
    return (
        select(r.id.label("resource_id"))
        .select_from(r)
        .join(m, m.resource_id == r.id)
        .where(r.repointed_id.is_(None), m.status == MembershipStatus.ACTIVE)
        .distinct()
    )


def base_resource_query(
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> Select[tuple[int]]:
    involved = _participating_columns(params)
    universe = _resource_universe().cte("resource_universe")

    if not involved:
        # No value field filtered or sorted -> the universe alone (every active
        # resource); only the id filter below can narrow it.
        base = universe
        conditions: list[ColumnElement[bool]] = []
    else:
        base_cte = construct_base_query_statement(licensed_sources)
        ranked = add_ranking(base_cte).cte("ranked")
        pivot = _add_pivot_columns(
            select(ranked.c.resource_id.label("resource_id")),
            involved,
            ranked.c.colname,
            lambda field_name: getattr(ranked.c, value_attr_for(field_name)),
        )
        pivot_cte = pivot.group_by(ranked.c.resource_id).cte("resource_pivot")

        # LEFT JOIN the licensed/coalesced pivot onto the membership universe: a
        # resource with no licensed values keeps its row (null-shell) but is
        # dropped by any field filter below.
        resource_base = select(universe.c.resource_id)
        for field_name in involved:
            resource_base = resource_base.add_columns(pivot_cte.c[field_name])
        base = resource_base.select_from(
            universe.outerjoin(
                pivot_cte, pivot_cte.c.resource_id == universe.c.resource_id
            )
        ).cte("resource_base")
        conditions = _build_field_conditions(base, params)

    stmt = select(base.c.resource_id)
    for cond in conditions:
        stmt = stmt.where(cond)
    if params.id is not None:
        stmt = stmt.where(base.c.resource_id == params.id)
    return stmt.order_by(*_build_sort_clauses(base, params, "resource_id"))


def _add_pivot_columns(
    stmt: Select,
    fields: Collection[str],
    colname_col: ColumnElement[Any],
    value_col_for: Callable[[str], ColumnElement[Any]],
) -> Select:
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


def _require_column(cte: CTE | Select, field_name: str) -> ColumnElement[Any]:
    """Return ``cte.c.<field_name>`` or raise if the narrowing dropped it.

    Conditions and sort clauses are derived from the same
    ``_participating_columns`` result as the pivot, so a missing column means
    the narrowing drifted -- raise (per the repo convention) rather than
    silently drop the filter/sort, which would return wrong rows.
    """
    obj = cte.c if isinstance(cte, CTE) else cte.selected_columns
    col = getattr(obj, field_name, None)
    if col is None:
        raise RuntimeError(
            f"source query references {field_name!r}, absent from the narrowed "
            "pivot; participating-columns narrowing is out of sync."
        )
    return col


def _build_field_conditions(
    cte: CTE | Select,
    params: OGFieldQueryParams,
) -> list[ColumnElement[bool]]:
    """Path-agnostic q-ILIKE + exact-match filters over the pivoted columns.

    Shared by the source and resource paths: every condition references a
    pivoted column via ``_require_column`` so a narrowing drift raises rather
    than silently dropping a filter. The ``source`` membership filter and the
    ``id`` identity filter are applied per-path by the base query builders;
    licensing is applied upstream in ``construct_base_query_statement``.
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


def _build_sort_clauses(
    cte: CTE | Select,
    params: OGFieldQueryParams,
    default: Literal["resource_id", "source_pk"] = "source_pk",
) -> list[Any]:
    direction = desc if params.sort_order == "desc" else asc
    # id/resource_id are identity aliases for the path's own id column (source_pk
    # on the source list, resource_id on the resource list).
    sort_by = default if params.sort_by in {"id", "resource_id"} else params.sort_by
    sort_col = _require_column(cte, sort_by)

    if sort_by == default:
        return [direction(sort_col).nulls_last()]

    return [
        direction(sort_col).nulls_last(),
        asc(_require_column(cte, default)),
    ]
