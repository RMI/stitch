"""Declarative mixin: shared OG field columns + query classmethods."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar, Self

from sqlalchemy import (
    ColumnElement,
    Float,
    Integer,
    Select,
    String,
    asc,
    desc,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, declarative_mixin, mapped_column

from stitch.api.entities import OGFieldFilterOptionField, OGFieldQueryParams
from stitch.ogsi.model import LocationType
from stitch.ogsi.model.types import (
    FieldStatus,
    PrimaryHydrocarbonGroup,
    ProductionConventionality,
)


@declarative_mixin
class OGFieldQueryMixin:
    """Shared OG field columns and query classmethods.

    Provides the full set of domain columns (aligned with OilGasFieldBase,
    minus owners/operators) and classmethods for filtered, sorted, paginated
    queries.  Subclasses may override ``_base_query`` to customise the FROM
    clause (e.g. adding joins) while inheriting conditions, sorting, and
    pagination logic.
    """

    # ------------------------------------------------------------------
    # Query field configuration
    # ------------------------------------------------------------------

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
        "source",
        "field_status",
        "location_type",
        "production_conventionality",
        "primary_hydrocarbon_group",
    )

    # ------------------------------------------------------------------
    # Shared column declarations
    # ------------------------------------------------------------------

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    name_local: Mapped[str | None] = mapped_column(String, nullable=True)
    state_province: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    basin: Mapped[str | None] = mapped_column(String, nullable=True)
    reservoir_formation: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    discovery_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    production_start_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fid_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Enum/Literal columns
    location_type: Mapped[LocationType | None] = mapped_column(
        default=None, nullable=True
    )
    production_conventionality: Mapped[ProductionConventionality | None] = (
        mapped_column(default=None, nullable=True)
    )
    primary_hydrocarbon_group: Mapped[PrimaryHydrocarbonGroup | None] = mapped_column(
        default=None, nullable=True
    )
    field_status: Mapped[FieldStatus | None] = mapped_column(
        default=None, nullable=True
    )

    # ------------------------------------------------------------------
    # Public query classmethods
    # ------------------------------------------------------------------

    @classmethod
    async def query(
        cls,
        session: AsyncSession,
        params: OGFieldQueryParams,
    ) -> Sequence[Self]:
        """Execute a filtered, sorted, paginated query and return (rows, total)."""
        base = cls._base_query(params)
        stmt = cls._apply_pagination(base, params)
        rows = (await session.scalars(stmt)).all()
        return rows

    @classmethod
    async def count(
        cls,
        session: AsyncSession,
        params: OGFieldQueryParams | None = None,
    ) -> int:
        """Return the total number of matching rows (unfiltered when params is None)."""
        if params is None:
            stmt = select(func.count()).select_from(cls)
        else:
            stmt = select(func.count()).select_from(cls._base_query(params).subquery())
        return await session.scalar(stmt) or 0

    @classmethod
    async def distinct_values(
        cls,
        session: AsyncSession,
        field: OGFieldFilterOptionField,
    ) -> list[str]:
        """Return distinct non-null, non-empty values for a supported text field."""
        col = getattr(cls, field)

        stmt = (
            select(col)
            .where(col.is_not(None))
            .where(col != "")
            .distinct()
            .order_by(asc(col))
        )
        return list((await session.scalars(stmt)).all())

    # ------------------------------------------------------------------
    # Internal helpers (overridable)
    # ------------------------------------------------------------------

    @classmethod
    def _base_query[QM: OGFieldQueryMixin](
        cls: type[QM], params: OGFieldQueryParams
    ) -> Select[tuple[QM]]:
        """Filtered + sorted SELECT with no pagination.

        Override this in subclasses to modify the FROM clause (e.g. add joins).
        """
        stmt: Select[tuple[QM]] = select(cls).distinct()
        for cond in cls._build_conditions(params):
            stmt = stmt.where(cond)
        return cls._apply_sort(stmt, params)

    @classmethod
    def _build_conditions(cls, params: OGFieldQueryParams) -> list[ColumnElement[bool]]:
        """Build WHERE conditions from filter params."""
        conditions: list[ColumnElement[bool]] = []

        if params.q:
            q_term = f"%{params.q}%"
            q_conds: list[ColumnElement[bool]] = []
            for field_name in cls._q_fields:
                col: ColumnElement[bool] | None = getattr(cls, field_name, None)
                if col is not None:
                    q_conds.append(col.ilike(q_term))
            if q_conds:
                conditions.append(or_(*q_conds))

        for field_name in cls._exact_match_fields:
            value = getattr(params, field_name, None)
            if value is not None:
                col = getattr(cls, field_name, None)
                if col is not None:
                    conditions.append(col == value)

        return conditions

    @classmethod
    def _apply_sort[QM: OGFieldQueryMixin](
        cls: type[QM], stmt: Select[tuple[QM]], params: OGFieldQueryParams
    ) -> Select[tuple[QM]]:
        """Apply ORDER BY with id tie-breaker."""
        sort_col = getattr(cls, params.sort_by)
        direction = desc if params.sort_order == "desc" else asc
        stmt = stmt.order_by(direction(sort_col).nulls_last())
        if params.sort_by != "id":
            stmt = stmt.order_by(asc(cls.id))
        return stmt

    @classmethod
    def _apply_pagination[QM: OGFieldQueryMixin](
        cls: type[QM], stmt: Select[tuple[QM]], params: OGFieldQueryParams
    ) -> Select[tuple[QM]]:
        """Apply offset/limit for pagination."""
        return stmt.offset(params.offset).limit(params.limit)
