"""v2 read path for resource list queries (phases 1 + 2).

Reads the precomputed ``og_field_resource_query_view`` projection instead of
coalescing live source rows at query time. This is the drop-in replacement for
``og_field_resource_actions.query()`` and must match its behavior exactly, save
for the two documented divergences:

1. ``params.source`` is ignored; only ``licensed_sources`` filters sources.
2. Two ACTIVE memberships of the same source key resolve by lowest ``source_id``
   (deterministic ``ORDER BY priority, source_id``) rather than ``max(value)``.

The coalescing winner is selected identically in both phases -- a window
function ``row_number() OVER (PARTITION BY resource_id ORDER BY priority ASC,
source_id ASC)`` keeping ``rn == 1`` -- so filtered/sorted values in phase 1
match the hydrated values in phase 2. This primitive is portable across
Postgres and SQLite >= 3.25 (unlike Postgres-only ``DISTINCT ON``).
"""

from __future__ import annotations

from collections.abc import Collection
from typing import get_args

from fastapi import HTTPException
from sqlalchemy import asc, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.entities import (
    FilterOptionField,
    OGFieldFilterOptionsParams,
    OGFieldQueryParams,
)
from stitch.ogsi.model import OGFieldListItemView
from stitch.ogsi.model.og_field import OilGasFieldBase
from stitch.ogsi.model.types import OGSISrcKey

from .model import (
    MembershipModel,
    MembershipStatus,
    OGFieldResourceQueryView,
    OilGasFieldSourceModel,
    ResourceModel,
)
from .model.og_field_resource_query_view import (
    FIELD_TO_VALUE_COLUMN,
    VALUE_JSON_FIELDS,
    VALUE_NUM_FIELDS,
)

# Year fields are the value_num fields minus latitude/longitude. Years coerce
# to int on hydrate; latitude/longitude stay float.
_YEAR_FIELDS = frozenset(VALUE_NUM_FIELDS) - {"latitude", "longitude"}
_JSON_FIELDS = frozenset(VALUE_JSON_FIELDS)
_MODEL_FIELDS = tuple(OilGasFieldBase.model_fields)
_FILTER_OPTION_FIELDS: frozenset[str] = frozenset(get_args(FilterOptionField))


def _licensed_list(
    licensed_sources: Collection[OGSISrcKey] | None,
) -> list[OGSISrcKey] | None:
    """Dedupe-preserving list, or None for the no-filter case."""
    if licensed_sources is None:
        return None
    return list(dict.fromkeys(licensed_sources))


def _winner_row_number(view: type[OGFieldResourceQueryView]):
    """Window: lowest (priority, source_id) per resource_id is the winner (rn == 1)."""
    return (
        func.row_number()
        .over(
            partition_by=view.resource_id,
            order_by=(view.priority.asc(), view.source_id.asc()),
        )
        .label("rn")
    )


def _coalesced_value_cte(field: str, licensed_list: list[OGSISrcKey] | None):
    """Build a CTE of (resource_id, v) for the winning licensed value of one field.

    The winner is the row with the lowest (priority, source_id) — identical to
    the window used in ``query_v2_ids``.  Returns a named CTE ``cv_<field>``.
    """
    view = OGFieldResourceQueryView
    value_col = getattr(view, FIELD_TO_VALUE_COLUMN[field])
    sub = select(
        view.resource_id, value_col.label("v"), _winner_row_number(view)
    ).where(view.column_name == field)
    if licensed_list is not None:
        sub = sub.where(view.source.in_(licensed_list))
    sub = sub.subquery()
    return select(sub.c.resource_id, sub.c.v).where(sub.c.rn == 1).cte(f"cv_{field}")


async def query_v2_ids(
    session: AsyncSession,
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> tuple[list[int], int]:
    """Phase 1: filtered/sorted/paginated resource ids + total (before pagination)."""
    if params.sort_by == "source":
        raise HTTPException(
            status_code=422,
            detail="sort_by=source is not supported for resource list queries.",
        )

    view = OGFieldResourceQueryView
    licensed_list = _licensed_list(licensed_sources)

    # 1. Universe: every (non-repointed) resource with an ACTIVE membership,
    #    NOT licensing-filtered, so an all-unlicensed resource still appears as a
    #    null-shell. Derived from memberships (NOT the projection) to match
    #    query()'s universe exactly: refresh emits zero projection rows for an
    #    all-null source, so a projection-derived universe would drop a resource
    #    whose only source is all-null -- query() still returns it (total=1).
    universe = (
        select(MembershipModel.resource_id)
        .join(ResourceModel, ResourceModel.id == MembershipModel.resource_id)
        .where(
            MembershipModel.status == MembershipStatus.ACTIVE,
            ResourceModel.repointed_id.is_(None),
        )
        .distinct()
        .cte("universe")
    )
    universe_resource_id = universe.c.resource_id

    # 2. Involved fields: sort field (if a scalar, not id/resource_id), exact-match
    #    fields with a value (except id, handled directly), and the 5 q-fields when
    #    q is set. JSON fields are never involved -> no JSON CTEs in phase 1.
    involved: list[str] = []

    def _add(field: str) -> None:
        if field not in involved:
            involved.append(field)

    if params.sort_by not in {"id", "resource_id"}:
        _add(params.sort_by)

    for field in OilGasFieldSourceModel._exact_match_fields:
        if field == "id":
            continue
        if getattr(params, field, None) is not None:
            _add(field)

    if params.q:
        for field in OilGasFieldSourceModel._q_fields:
            _add(field)

    # 3. Coalesce every involved field in ONE windowed pass + GROUP BY pivot.
    #    A single GROUP BY derived table (which SQLite/Postgres can hash- or
    #    auto-index for the universe join) — NOT one windowed CTE per field
    #    LEFT JOINed individually. The latter forces SQLite to nested-loop
    #    scan an unindexable windowed CTE per universe row -> O(n^2) at scale.
    #    The winner is still rn == 1 over (priority, source_id), identical to
    #    hydrate_v2, so phase-1 values match phase-2 hydration.
    pivot = None
    if involved:
        rn = (
            func.row_number()
            .over(
                partition_by=(view.resource_id, view.column_name),
                order_by=(view.priority.asc(), view.source_id.asc()),
            )
            .label("rn")
        )
        ranked_sel = select(
            view.resource_id, view.column_name, view.value_text, view.value_num, rn
        ).where(view.column_name.in_(involved))
        if licensed_list is not None:
            ranked_sel = ranked_sel.where(view.source.in_(licensed_list))
        ranked = ranked_sel.subquery()
        pivot_cols = [
            func.max(
                case(
                    (
                        ranked.c.column_name == field,
                        ranked.c[FIELD_TO_VALUE_COLUMN[field]],
                    )
                )
            ).label(field)
            for field in involved
        ]
        pivot = (
            select(ranked.c.resource_id, *pivot_cols)
            .where(ranked.c.rn == 1)
            .group_by(ranked.c.resource_id)
            .cte("coalesced")
        )

    # 4. LEFT JOIN the pivot so null-shells (no licensed/involved rows) survive.
    selected = select(universe_resource_id.label("resource_id"))
    if pivot is not None:
        for field in involved:
            selected = selected.add_columns(pivot.c[field].label(field))
    joined = selected.select_from(universe)
    if pivot is not None:
        joined = joined.join(
            pivot, pivot.c.resource_id == universe_resource_id, isouter=True
        )

    # 5. Filters on the coalesced (post-licensing) values.
    if params.id is not None:
        joined = joined.where(universe_resource_id == params.id)

    for field in OilGasFieldSourceModel._exact_match_fields:
        if field == "id":
            continue
        value = getattr(params, field, None)
        if value is not None:
            joined = joined.where(pivot.c[field] == value)

    if params.q:
        q_term = f"%{params.q}%"
        joined = joined.where(
            or_(
                *[
                    pivot.c[field].ilike(q_term)
                    for field in OilGasFieldSourceModel._q_fields
                ]
            )
        )

    filtered = joined.subquery()

    # 6. Count before pagination.
    total = (await session.scalar(select(func.count()).select_from(filtered))) or 0

    # 7. Order by (mirror _build_sort_clauses) then paginate.
    page_stmt = select(filtered.c.resource_id)
    direction = desc if params.sort_order == "desc" else asc
    sort_id = filtered.c.resource_id
    if params.sort_by in {"id", "resource_id"}:
        page_stmt = page_stmt.order_by(direction(sort_id).nulls_last())
    else:
        sort_col = filtered.c[params.sort_by]
        page_stmt = page_stmt.order_by(direction(sort_col).nulls_last(), asc(sort_id))

    page_stmt = page_stmt.offset(params.offset).limit(params.limit)

    ids = list((await session.scalars(page_stmt)).all())
    return ids, total


def _coerce_value(field: str, row: OGFieldResourceQueryView):
    """Pull the routed column off a winning row, coercing years to int."""
    column = FIELD_TO_VALUE_COLUMN[field]
    if field in _JSON_FIELDS:
        return row.value_json
    if column == "value_num":
        if row.value_num is None:
            return None
        return int(row.value_num) if field in _YEAR_FIELDS else float(row.value_num)
    return row.value_text


async def hydrate_v2(
    session: AsyncSession,
    resource_ids: list[int],
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> list[OGFieldListItemView]:
    """Phase 2: hydrate the given resource ids into ordered list items."""
    if not resource_ids:
        return []

    view = OGFieldResourceQueryView
    licensed_list = _licensed_list(licensed_sources)

    stmt = select(view).where(view.resource_id.in_(resource_ids))
    if licensed_list is not None:
        stmt = stmt.where(view.source.in_(licensed_list))
    rows = list((await session.scalars(stmt)).all())

    # Group winning rows per (resource_id, column_name) by min(priority, source_id).
    # Every fetched row is a present value (the build skipped only None), so
    # "present rows" == "the rows we fetched"; "" and [] are valid winners.
    winners: dict[int, dict[str, OGFieldResourceQueryView]] = {}
    for row in rows:
        per_field = winners.setdefault(row.resource_id, {})
        current = per_field.get(row.column_name)
        if current is None or (row.priority, row.source_id) < (
            current.priority,
            current.source_id,
        ):
            per_field[row.column_name] = row

    items_by_id: dict[int, OGFieldListItemView] = {}
    for resource_id in resource_ids:
        if resource_id in items_by_id:
            continue
        per_field = winners.get(resource_id, {})
        data_kwargs: dict = {}
        provenance: dict[str, OGSISrcKey | None] = {}
        for field in _MODEL_FIELDS:
            win = per_field.get(field)
            if win is None:
                data_kwargs[field] = None
                provenance[field] = None
            else:
                data_kwargs[field] = _coerce_value(field, win)
                provenance[field] = win.source
        items_by_id[resource_id] = OGFieldListItemView(
            id=resource_id,
            data=OilGasFieldBase(**data_kwargs),
            provenance=provenance,
        )

    return [items_by_id[rid] for rid in resource_ids]


async def query_v2(
    session: AsyncSession,
    params: OGFieldQueryParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> tuple[list[OGFieldListItemView], int]:
    """Drop-in replacement for ``query()``: phase 1 ids + phase 2 hydration."""
    ids, total = await query_v2_ids(session, params, licensed_sources)
    items = await hydrate_v2(session, ids, licensed_sources)
    return items, total


async def filter_options_v2(
    session: AsyncSession,
    params: OGFieldFilterOptionsParams,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> list[str]:
    """Return distinct coalesced values for one filterable field (v2 read path).

    Drop-in replacement for ``filter_options()``.  Reads the precomputed
    ``og_field_resource_query_view`` projection.  Licensing semantics are
    identical to ``query_v2``: ``licensed_sources=None`` ⇒ no source filter;
    a collection (incl. empty ``frozenset()``) ⇒ ``source IN (licensed)``.
    ``params.source`` is ignored, as in Task 4.
    """
    if params.field not in _FILTER_OPTION_FIELDS:
        raise HTTPException(
            status_code=422,
            detail=f"field={params.field} is not supported for resource filter options.",
        )

    licensed_list = _licensed_list(licensed_sources)
    cte = _coalesced_value_cte(params.field, licensed_list)
    v = cte.c.v
    stmt = select(v).where(v.is_not(None), v != "").distinct().order_by(v)
    values = await session.scalars(stmt)
    return list(values.all())
