from __future__ import annotations

from typing import Any, ClassVar, Self

from pydantic import TypeAdapter
from sqlalchemy import (
    Float,
    Integer,
    String,
    JSON,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column
from stitch.ogsi.model import OGFieldSource
from stitch.ogsi.model.types import (
    FieldStatus,
    LocationType,
    OGSISrcKey,
    PrimaryHydrocarbonGroup,
    ProductionConventionality,
)

from stitch.api.db.model.types import PORTABLE_BIGINT

from .common import Base
from .mixins import TimestampMixin, UserAuditMixin


class OilGasFieldSourceModel(TimestampMixin, UserAuditMixin, Base):
    """A single OG field source record (canonicalized), feedable into a Resource."""

    type_adapter: ClassVar[TypeAdapter[OGFieldSource]] = TypeAdapter(OGFieldSource)

    __tablename__ = "oil_gas_field_source"

    id: Mapped[int] = mapped_column(PORTABLE_BIGINT, primary_key=True)

    # SqlAlchemy will translate Literal types into Enums
    source: Mapped[OGSISrcKey] = mapped_column(nullable=False)

    # Domain columns (aligned with OilGasFieldBase)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    basin: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    name_local: Mapped[str | None] = mapped_column(String, nullable=True)
    state_province: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    reservoir_formation: Mapped[str | None] = mapped_column(String, nullable=True)
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

    # JSON columns
    owners: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    operators: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    def as_entity(self) -> OGFieldSource:
        return self.__class__.type_adapter.validate_python(self)

    @classmethod
    def from_entity(cls, entity: OGFieldSource) -> Self:
        mapper = inspect(cls)
        column_keys = {col.key for col in mapper.columns}
        filtered = {k: v for k, v in entity.model_dump().items() if k in column_keys}
        return cls(**filtered)
