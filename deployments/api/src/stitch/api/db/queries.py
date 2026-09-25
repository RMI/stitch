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
    OGFieldResourceStateModel,
    OGFieldSourcePriority,
    OilGasFieldSourceModel,
    OilGasFieldSourceValueModel,
    ResourceModel,
)
from stitch.api.db.model.oil_gas_field_source_value import value_attr_for
from stitch.api.entities import FILTER_OPTION_FIELDS, OGFieldQueryParams
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


def _filter_values(params: OGFieldQueryParams, field_name: str) -> list[Any]:
    """The values an exact-match filter is set to, as a list.

    Multi-select fields arrive as lists; the rest are scalars, returned as a
    list of one so callers need only one shape. An unset filter and an empty
    list both come back empty, which means "not filtering on this field" — an
    empty list must never reach SQL as `IN ()`, which matches nothing.
    """
    value = getattr(params, field_name, None)
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


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
        if _filter_values(params, field):
            participating.append(field)

    if params.q:
        participating += Q_FIELDS

    return list(dict.fromkeys(participating))


def _override_join(resource_id: Any) -> ColumnElement[bool]:
    """Join condition matching an override row to its value row."""
    m = MembershipModel
    v = OilGasFieldSourceValueModel
    o = OGFieldResourceSourcePriority
    return and_(
        o.resource_id == resource_id,
        o.source_pk == m.source_pk,
        o.source == m.source,
        o.colname == v.colname,
    )


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

    active_src = (
        select(
            r.id.label("resource_id"),
            m.source.label("source"),
            m.source_pk.label("source_pk"),
            # Two columns, not a collapsed COALESCE: tiering (curated records above
            # default ones) needs override_priority NULLS LAST as a distinct sort
            # key. Absent an override row for the value, override_priority is NULL
            # and only default_priority ranks the row (identical to no overrides).
            o.priority.label("override_priority"),
            p.priority.label("default_priority"),
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
        .outerjoin(o, _override_join(r.id))
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
    """Attach the tiered coalesce rank ``rn`` to every candidate row (no cut).

    Single source of truth for "who beats whom", shared by the winner cut
    (``add_ranking`` -> ``rn == 1``), the per-field listing
    (``field_source_candidates``), and the precomputed-state builder
    (``resource_state_rows``) so they can't drift. ``rn == 1`` is the winner
    within each ``(resource_id, colname)`` partition.

    The order is tiered: curated records (an override row exists for the value, so
    ``override_priority`` is NOT NULL) rank above default ones (``NULLS LAST`` is
    the tier split), then global default priority, then source/source_pk
    tiebreaks. No empty-string handling is needed here: empty text can't be
    persisted (write-path skip + DB CHECK ``ck_source_value_text_nonempty``, see
    ``model.oil_gas_field_source_value``).
    """
    cols = base_cte.c
    return (
        select(base_cte)
        .add_columns(
            func.row_number()
            .over(
                partition_by=(cols.resource_id, cols.colname),
                # Tiered: curated records (override_priority NOT NULL) rank above
                # default ones (NULLS LAST is the tier split), then global default
                # priority, then source/source_pk tiebreaks.
                order_by=(
                    cols.override_priority.asc().nulls_last(),
                    cols.default_priority.asc(),
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


def resource_state_rows(
    resource_ids: Collection[int] | None = None,
) -> Select[tuple[Any, ...]]:
    """Rows to persist into ``og_field_resource_state`` for the given resources.

    Every ranked candidate value per ``(resource, field)`` -- the full candidate
    list, not just the winner. This is the same tiered coalescing the live path
    uses (built on the shared ``_ranked`` CTE, so the winner order never forks) but
    with *no* licensing filter: all candidates are stored, and the read path
    applies the caller's licensing to pick their winner. Pass ``None`` to rebuild
    every resource; the base query already excludes repointed resources and
    inactive memberships, so a repointed id yields no rows (an effective delete on
    refresh).
    """
    base = construct_base_query_statement(resource_ids=resource_ids)
    ranked = _ranked(base)
    c = ranked.c
    return select(
        c.resource_id,
        c.colname,
        c.rn.label("rank"),
        c.source,
        c.source_pk,
        c.value_text,
        c.value_num,
        c.value_json,
    )


def coalesced_state_winner_rows(
    licensed_sources: Collection[OGSISrcKey] | None = None,
    resource_ids: Collection[int] | None = None,
) -> Select[tuple[Any, ...]]:
    """Winning ``(value, source)`` per ``(resource, field)`` from the state table.

    The precomputed-table equivalent of ``add_ranking(construct_base_query_...)``:
    same output shape (``resource_id, colname, value_text, value_num, value_json,
    source, source_pk``), but read off ``og_field_resource_state`` instead of
    rebuilding the 5-table coalescing CTE. Licensing is applied here (the stored
    rows are the full unlicensed candidate list): filter to ``licensed_sources``,
    then take the top surviving ``rank`` per field -- exactly the "narrow by
    license, then rank" the live path does, so the winner is identical.
    """
    st = OGFieldResourceStateModel
    base = select(
        st.resource_id,
        st.colname,
        st.rank,
        st.source,
        st.source_pk,
        st.value_text,
        st.value_num,
        st.value_json,
    )
    if licensed_sources is not None:
        base = base.where(st.source.in_(list(dict.fromkeys(licensed_sources))))
    if resource_ids is not None:
        base = base.where(st.resource_id.in_(list(dict.fromkeys(resource_ids))))
    licensed = base.cte("licensed_state")
    ranked = (
        select(licensed)
        .add_columns(
            func.row_number()
            .over(
                partition_by=(licensed.c.resource_id, licensed.c.colname),
                order_by=(licensed.c.rank.asc(),),
            )
            .label("win_rn")
        )
        .cte("licensed_state_ranked")
    )
    return select(
        ranked.c.resource_id,
        ranked.c.colname,
        ranked.c.value_text,
        ranked.c.value_num,
        ranked.c.value_json,
        ranked.c.source,
        ranked.c.source_pk,
    ).where(ranked.c.win_rn == 1)


def filter_option_rows(
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> Select[tuple[str, str]]:
    """Distinct winning ``(colname, value)`` pairs for every filterable field.

    Reads the coalesced winners off the precomputed state table (see
    ``coalesced_state_winner_rows``) rather than rebuilding the ranking CTE, then
    keeps the distinct non-null text values of the filterable fields.
    """
    winners = coalesced_state_winner_rows(licensed_sources).cte("filter_option_winners")
    c = winners.c
    return (
        select(c.colname, c.value_text)
        .where(
            c.colname.in_(FILTER_OPTION_FIELDS),
            c.value_text.is_not(None),
        )
        .distinct()
        .order_by(c.colname, c.value_text)
    )


def field_source_candidates(
    resource_id: int,
    field: str,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> Select[tuple[Any, ...]]:
    """Every source record's value for one field of one resource, winner-first.

    The same tiered ranking as coalescing, sharing ``_ranked`` with
    ``add_ranking`` -- this is that ranking *without* the ``rn == 1`` cut, so it
    returns all candidate rows for the field ordered best-first (by ``rn``).
    Empty text can't be persisted (write-path skip + DB CHECK), so the row set is
    exactly the field's eligible sources. ``is_override`` is true when a curator
    has re-ranked this record for the field (an override row exists).
    Powers both the read endpoint and the write-path eligibility/no-op checks.
    """
    base = construct_base_query_statement(licensed_sources, resource_ids=[resource_id])
    ranked = _ranked(base)
    c = ranked.c
    return (
        select(
            c.source,
            c.source_pk,
            c.value_text,
            c.value_num,
            c.value_json,
            c.override_priority.is_not(None).label("is_override"),
        )
        .where(c.colname == field)
        .order_by(c.rn)
    )


def resource_source_rows(
    resource_ids: Collection[int],
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> Select[tuple[Any, ...]]:
    """Raw per-source value rows (with the source header) for ``source_data``.

    The detail view's coalesced winners come from the precomputed state table
    (``coalesced_state_winner_rows``); this supplies the *other* half of the detail
    payload -- the raw per-source records. ``source_data`` groups by ``source_pk``
    and ignores rank (``utils._source_data_from_rows``), so this query does **no**
    ranking: it is just the active, licensed memberships of the given non-repointed
    resources joined to their source header + value rows. Rows are ordered by the
    global default ``priority`` (then source, source_pk, colname) so grouping by
    source yields sources best-priority-first, matching the coalesced ordering.
    """
    s = OilGasFieldSourceModel
    v = OilGasFieldSourceValueModel
    m = MembershipModel
    r = ResourceModel
    p = OGFieldSourcePriority
    stmt = (
        select(
            r.id.label("resource_id"),
            m.source.label("source"),
            m.source_pk.label("source_pk"),
            v.colname.label("colname"),
            v.value_text,
            v.value_num,
            v.value_json,
            s.source_record,
        )
        .select_from(m)
        .join(r, r.id == m.resource_id)
        .join(p, p.source == m.source)
        .join(s, and_(s.id == m.source_pk, s.source == m.source))
        .join(v, v.source_pk == m.source_pk)
        .where(
            r.repointed_id.is_(None),
            m.status == MembershipStatus.ACTIVE,
        )
    )
    if licensed_sources is not None:
        stmt = stmt.where(m.source.in_(list(dict.fromkeys(licensed_sources))))
    if resource_ids is not None:
        stmt = stmt.where(m.resource_id.in_(list(dict.fromkeys(resource_ids))))
    return stmt.order_by(p.priority, m.source, m.source_pk, v.colname)


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
        # Coalesced winners come from the precomputed state table (licensing
        # applied there), not a per-request rebuild of the ranking CTE.
        winners = coalesced_state_winner_rows(licensed_sources).cte("ranked")
        pivot = _add_pivot_columns(
            select(winners.c.resource_id.label("resource_id")),
            involved,
            winners.c.colname,
            lambda field_name: getattr(winners.c, value_attr_for(field_name)),
        )
        pivot_cte = pivot.group_by(winners.c.resource_id).cte("resource_pivot")

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
        values = _filter_values(params, field_name)
        if not values:
            continue
        # IN over one value is the same predicate `== value` produced before, so
        # single-valued filters are unchanged.
        conditions.append(_require_column(cte, field_name).in_(values))

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
