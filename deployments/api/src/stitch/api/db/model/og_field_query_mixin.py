"""Declarative mixin: long-aware filter/sort/paginate over source records.

A source record is no longer one wide row -- its attributes live in the long
``oil_gas_field_source_values`` table. This mixin pivots each record's value
rows back into a wide, one-row-per-record subquery (restricted to records with
an active membership), then applies the same conditions/sort/pagination the
endpoint always used. Numeric attributes pivot out of ``value_num`` so ordering
is numerically correct without casts.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Any, ClassVar, Self

from sqlalchemy import (
    ColumnElement,
    asc,
    case,
    desc,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_mixin

from stitch.api.entities import OGFieldQueryParams, OGSI_SOURCE_DEFAULT
from stitch.ogsi.model.types import OGSISrcKey

from .membership import MembershipModel, MembershipStatus
from .oil_gas_field_source_value import (
    ATTRIBUTE_KINDS,
    ATTRIBUTE_NAMES,
    OilGasFieldSourceValueModel,
    ValueKind,
    value_attr_for,
)


@declarative_mixin
class OGFieldQueryMixin:
    """Long-aware query classmethods for source-record models.

    The host model must declare ``id`` and ``source`` columns; attribute values
    are read from the related ``oil_gas_field_source_values`` rows.
    """

    _q_fields: ClassVar[tuple[str, ...]] = (
        "name",
        "name_local",
        "basin",
        "state_province",
        "region",
    )

    _exact_match_fields: ClassVar[tuple[str, ...]] = (
        *_q_fields,
        "id",
        "country",
        "field_status",
        "location_type",
        "production_conventionality",
        "primary_hydrocarbon_group",
    )

    __primary_sort_col__: ClassVar[str] = "id"

    # ------------------------------------------------------------------
    # Pivot: one wide row per source record (active-membership only)
    # ------------------------------------------------------------------

    @classmethod
    def _source_pivot(cls, licensed_sources: Collection[OGSISrcKey] | None = None):
        """Build a CTE with one row per source record and a column per attr."""
        v = OilGasFieldSourceValueModel
        active_membership = (
            select(1)
            .where(MembershipModel.source_pk == cls.id)
            .where(MembershipModel.status == MembershipStatus.ACTIVE)
            .exists()
        )
        stmt = (
            select(cls.id.label("id"), cls.source.label("source"))
            .select_from(cls)
            .outerjoin(v, v.source_pk == cls.id)
            .where(active_membership)
        )
        if licensed_sources is not None:
            stmt = stmt.where(cls.source.in_(list(dict.fromkeys(licensed_sources))))
        stmt = stmt.group_by(cls.id, cls.source)
        # JSON attributes (owners/operators) are neither filterable nor
        # sortable, so they are omitted -- this also avoids max(jsonb), which
        # Postgres has no aggregate for.
        for field_name in ATTRIBUTE_NAMES:
            if ATTRIBUTE_KINDS[field_name] is ValueKind.JSON:
                continue
            value_col = getattr(v, value_attr_for(field_name))
            stmt = stmt.add_columns(
                func.max(case((v.colname == field_name, value_col))).label(field_name)
            )
        return stmt.cte("source_pivot")

    @staticmethod
    def _pivot_column(pivot, field_name: str):
        return getattr(pivot.c, field_name, None)

    # ------------------------------------------------------------------
    # Public query classmethods
    # ------------------------------------------------------------------

    @classmethod
    async def query(
        cls,
        session: AsyncSession,
        params: OGFieldQueryParams,
        licensed_sources: Collection[OGSISrcKey] | None = None,
    ) -> Sequence[Self]:
        """Filtered, sorted, paginated source records (as ORM instances)."""
        pivot = cls._source_pivot(licensed_sources)
        stmt = select(pivot.c.id)
        for cond in cls._build_conditions(params, pivot, licensed_sources):
            stmt = stmt.where(cond)
        stmt = stmt.order_by(*cls._create_sort_clauses(params, pivot))
        stmt = stmt.offset(params.offset).limit(params.limit)

        ids = list((await session.scalars(stmt)).all())
        if not ids:
            return []
        headers = (await session.scalars(select(cls).where(cls.id.in_(ids)))).all()
        by_id = {h.id: h for h in headers}
        return [by_id[i] for i in ids if i in by_id]

    @classmethod
    async def count(
        cls,
        session: AsyncSession,
        params: OGFieldQueryParams | None = None,
        licensed_sources: Collection[OGSISrcKey] | None = None,
    ) -> int:
        """Count matching source records (all active-membership records when no params)."""
        pivot = cls._source_pivot(licensed_sources)
        stmt = select(pivot.c.id)
        if params is not None:
            for cond in cls._build_conditions(params, pivot, licensed_sources):
                stmt = stmt.where(cond)
        return (
            await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )

    # ------------------------------------------------------------------
    # Condition / sort builders (operate on the pivot's labeled columns)
    # ------------------------------------------------------------------

    @classmethod
    def _build_conditions(
        cls,
        params: OGFieldQueryParams,
        pivot,
        licensed_sources: Collection[OGSISrcKey] | None = None,
    ) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = []

        if params.q:
            q_term = f"%{params.q}%"
            q_conds: list[ColumnElement[bool]] = []
            for field_name in cls._q_fields:
                col = cls._pivot_column(pivot, field_name)
                if col is not None:
                    q_conds.append(col.ilike(q_term))
            if q_conds:
                conditions.append(or_(*q_conds))

        for field_name in cls._exact_match_fields:
            value = getattr(params, field_name, None)
            if value is None:
                continue
            col = cls._pivot_column(pivot, field_name)
            if col is not None:
                conditions.append(col == value)

        sources = list(dict.fromkeys(getattr(params, "source", OGSI_SOURCE_DEFAULT)))
        conditions.append(pivot.c.source.in_(sources))
        if licensed_sources is not None:
            conditions.append(pivot.c.source.in_(list(dict.fromkeys(licensed_sources))))

        return conditions

    @classmethod
    def _create_sort_clauses(cls, params: OGFieldQueryParams, pivot) -> list[Any]:
        clauses: list[Any] = []
        sort_col = cls._pivot_column(pivot, params.sort_by)
        if sort_col is not None:
            direction = desc if params.sort_order == "desc" else asc
            clauses.append(direction(sort_col).nulls_last())
        if params.sort_by != cls.__primary_sort_col__:
            primary_sort_col = cls._pivot_column(pivot, cls.__primary_sort_col__)
            if primary_sort_col is not None:
                clauses.append(asc(primary_sort_col))
        return clauses
