"""Denormalized view of og field resource id, connected source data (via memberships), and priority"""

from __future__ import annotations
from collections.abc import Sequence
from typing import Any, Final, Self, override

from sqlalchemy import (
    JSON,
    ColumnElement,
    Connection,
    ForeignKey,
    Integer,
    Select,
    String,
    UnaryExpression,
    asc,
    desc,
    select,
    text,
    or_,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from stitch.api.entities import OGFieldQueryParams
from stitch.ogsi.model import OGSISrcKey
from stitch.ogsi.model.og_field import OilGasFieldBase

from .common import Base
from .og_field_query_mixin import OGFieldQueryMixin
from .og_field_source_priority import OGFieldSourcePriority
from .oil_gas_field_source import OilGasFieldSourceModel
from .membership import MembershipModel, MembershipStatus
from .resource import ResourceModel


class OGFieldResourceSourcesPrioritizedView(OGFieldQueryMixin, Base):
    VIEW_NAME: Final[str] = "og_field_resource_sources_prioritized"

    __tablename__ = VIEW_NAME
    __table_args__ = {"info": {"is_view": True}}

    __primary_sort_col__ = "resource_id"

    resource_id: Mapped[int] = mapped_column(
        ForeignKey("og_field_resources.id"), nullable=False
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("oil_gas_field_sources.id"), nullable=False
    )
    # SqlAlchemy will translate Literal types into Enums
    source: Mapped[OGSISrcKey] = mapped_column(nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)

    # JSON columns
    owners: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    operators: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    @classmethod
    @override
    async def query(
        cls, session: AsyncSession, params: OGFieldQueryParams
    ) -> Sequence[Self]:
        # get all data that __would__ be displayed (based on user query, includes potentially restricted data)
        base = cls._base_query(params)
        return await super().query(session, params)

    @classmethod
    @override
    def _base_query(cls, params: OGFieldQueryParams):
        return select(cls).where(*cls._build_conditions(params))

    @classmethod
    @override
    def _create_sort_clauses(cls, params: OGFieldQueryParams):
        """Apply ORDER BY with id tie-breaker."""
        clauses: list[UnaryExpression[Any]] = []
        sc = getattr(cls, params.sort_by, None)
        if sc is not None and params.sort_by != "source":
            dir_ = desc if params.sort_order == "desc" else asc
            clauses.append(dir_(sc).nulls_last())
        if params.sort_by != cls.__primary_sort_col__:
            sc = getattr(cls, cls.__primary_sort_col__, None)
            if sc is not None:
                clauses.append(asc(sc))
        return clauses

    @staticmethod
    def create_view(conn: Connection) -> None:
        """Create the coalesced resource SQL view.

        Accepts a sync Connection — use with ``engine.begin()`` or
        ``async_conn.run_sync()`` for async contexts.
        """
        klass = __class__
        view_select = klass.build_view_select()
        compiled = view_select.compile(
            dialect=conn.dialect, compile_kwargs={"literal_binds": True}
        )
        if conn.dialect.name == "postgresql":
            ddl = f"CREATE OR REPLACE VIEW {klass.VIEW_NAME} AS {compiled}"
        else:
            ddl = f"CREATE VIEW IF NOT EXISTS {klass.VIEW_NAME} AS {compiled}"
        conn.execute(text(ddl))

    @staticmethod
    def build_view_select():
        """Build the SELECT statement for the view.

        The effective SQL is (generated from sqlalchemy's `compile` function):

        ```sql
        SELECT
            og_field_resources.id AS id,
            oil_gas_field_sources.id AS source_id,
            oil_gas_field_sources.source as source,
            og_field_source_priority.priority AS priority,
            oil_gas_field_sources.operators as operators
            oil_gas_field_sources.owners AS owners

            -- query mixin fields
            oil_gas_field_sources.name AS name,
            oil_gas_field_sources.country AS country,
            oil_gas_field_sources.name_local AS name_local,
            oil_gas_field_sources.state_province AS state_province,
            oil_gas_field_sources.region AS region,
            oil_gas_field_sources.basin AS basin,
            oil_gas_field_sources.reservoir_formation AS reservoir_formation,
            oil_gas_field_sources.latitude AS latitude,
            oil_gas_field_sources.longitude AS longitude,
            oil_gas_field_sources.discovery_year AS discovery_year,
            oil_gas_field_sources.production_start_year AS production_start_year,
            oil_gas_field_sources.fid_year AS fid_year,
            oil_gas_field_sources.location_type AS location_type,
            oil_gas_field_sources.production_conventionality AS production_conventionality,
            oil_gas_field_sources.primary_hydrocarbon_group AS primary_hydrocarbon_group,
            oil_gas_field_sources.field_status AS field_status
        FROM
            og_field_resources
            JOIN og_field_memberships ON og_field_memberships.resource_id = og_field_resources.id
            JOIN oil_gas_field_sources ON og_field_memberships.source_pk = oil_gas_field_sources.id
            JOIN og_field_source_priority ON oil_gas_field_sources.source = og_field_source_priority.source
        WHERE
            og_field_memberships.status = 'ACTIVE'
            AND og_field_resources.repointed_id IS NULL
        ORDER BY
            og_field_resources.id DESC,
            og_field_source_priority.priority ASC,
            oil_gas_field_sources.created DESC;
        ```
        """
        s = OilGasFieldSourceModel
        m = MembershipModel
        r = ResourceModel
        p = OGFieldSourcePriority

        base = (
            select(
                r.id.label("id"),
                s.id.label("source_id"),
                s.source.label("source"),
                p.priority.label("priority"),
            )
            .join(m, m.resource_id == r.id)
            .join(s, m.source_pk == s.id)
            .join(p, s.source == p.source)
            .where(m.status == MembershipStatus.ACTIVE, r.repointed_id.is_(None))
            .order_by(r.id.desc(), p.priority.asc(), s.created.desc())
        )

        for field_name in OilGasFieldBase.model_fields:
            col = getattr(s, field_name, None)
            if col is None:
                continue
            base = base.add_columns(col.label(field_name))

        return base
