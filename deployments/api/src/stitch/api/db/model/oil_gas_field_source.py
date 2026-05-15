from __future__ import annotations

from collections.abc import Collection
from typing import Any, ClassVar, override

from pydantic import TypeAdapter
from sqlalchemy import (
    JSON,
    inspect,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column
from stitch.ogsi.model import OGFieldSource
from stitch.ogsi.model.types import OGSISrcKey

from stitch.api.db.model.types import PORTABLE_BIGINT
from stitch.api.entities import OGFieldQueryParams, User

from .common import Base
from .membership import MembershipModel, MembershipStatus
from .mixins import TimestampMixin, UserAuditMixin
from .og_field_query_mixin import OGFieldQueryMixin


class OilGasFieldSourceModel(OGFieldQueryMixin, TimestampMixin, UserAuditMixin, Base):
    """A single OG field source record (canonicalized), feedable into a Resource."""

    type_adapter: ClassVar[TypeAdapter[OGFieldSource]] = TypeAdapter(OGFieldSource)

    __tablename__: str = "oil_gas_field_sources"

    id: Mapped[int] = mapped_column(PORTABLE_BIGINT, primary_key=True)

    # SqlAlchemy will translate Literal types into Enums
    source: Mapped[OGSISrcKey] = mapped_column(nullable=False)

    # JSON columns
    owners: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    operators: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    source_record: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    @classmethod
    @override
    def _base_query(
        cls,
        params: OGFieldQueryParams,
        licensed_sources: Collection[OGSISrcKey] | None = None,
    ):
        """Filter to sources with at least one active membership."""

        active_membership = (
            select(1)
            .where(MembershipModel.source_pk == cls.id)
            .where(MembershipModel.status == MembershipStatus.ACTIVE)
            .exists()
        )
        stmt = select(cls).where(active_membership)
        for cond in cls._build_conditions(params, licensed_sources=licensed_sources):
            stmt = stmt.where(cond)
        return stmt.order_by(*cls._create_sort_clauses(params))

    @classmethod
    def create_from_entity(cls, ent: OGFieldSource, created_by: User):
        cols = {col.key for col in inspect(cls).columns}
        kwargs = {k: val for k, val in ent.model_dump(mode="json").items() if k in cols}
        return cls(
            **kwargs, created_by_id=created_by.id, last_updated_by_id=created_by.id
        )

    def as_entity(self) -> OGFieldSource:
        return self.__class__.type_adapter.validate_python(self)

    @classmethod
    def from_entity(cls, entity: OGFieldSource):
        mapper = inspect(cls)
        column_keys = {col.key for col in mapper.columns}
        filtered = {k: v for k, v in entity.model_dump().items() if k in column_keys}
        return cls(**filtered)
