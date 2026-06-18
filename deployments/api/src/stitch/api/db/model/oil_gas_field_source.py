from __future__ import annotations

from typing import Any, ClassVar

from pydantic import TypeAdapter
from sqlalchemy.orm import Mapped, mapped_column, relationship
from stitch.ogsi.model import OGFieldSource
from stitch.ogsi.model.types import OGSISrcKey

from stitch.api.db.model.types import PORTABLE_BIGINT, StitchJson
from stitch.api.entities import User

from .common import Base
from .mixins import TimestampMixin, UserAuditMixin
from .og_field_query_mixin import OGFieldQueryMixin
from .oil_gas_field_source_value import ATTRIBUTE_NAMES, OilGasFieldSourceValueModel


class OilGasFieldSourceModel(OGFieldQueryMixin, TimestampMixin, UserAuditMixin, Base):
    """Header for a single OG field source record.

    Identity + raw payload only; the coalesced attributes live in long form on
    ``oil_gas_field_source_values`` (``values`` relationship).
    """

    type_adapter: ClassVar[TypeAdapter[OGFieldSource]] = TypeAdapter(OGFieldSource)

    __tablename__: str = "oil_gas_field_sources"

    id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT, primary_key=True, autoincrement=True
    )

    # SqlAlchemy will translate the Literal type into an Enum.
    source: Mapped[OGSISrcKey] = mapped_column(nullable=False)

    # Raw, non-coalesced original payload.
    source_record: Mapped[dict[str, Any]] = mapped_column(StitchJson, nullable=False)

    # Long-form coalesced attributes; eager-loaded so as_entity() stays sync.
    values: Mapped[list[OilGasFieldSourceValueModel]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @classmethod
    def create_from_entity(cls, ent: OGFieldSource, created_by: User):
        return cls._build(ent, created_by_id=created_by.id)

    @classmethod
    def from_entity(cls, entity: OGFieldSource):
        return cls._build(entity)

    @classmethod
    def _build(cls, ent: OGFieldSource, created_by_id: int | None = None):
        dumped = ent.model_dump(mode="json")
        kwargs: dict[str, Any] = {
            "source": dumped["source"],
            "source_record": dumped["source_record"],
        }
        if created_by_id is not None:
            kwargs["created_by_id"] = created_by_id
            kwargs["last_updated_by_id"] = created_by_id
        header = cls(**kwargs)
        header.values = [
            OilGasFieldSourceValueModel.from_attribute(colname, dumped[colname])
            for colname in ATTRIBUTE_NAMES
            if dumped.get(colname) is not None
        ]
        return header

    def as_entity(self) -> OGFieldSource:
        # Materialize absent attributes as None (the long table is dense).
        data: dict[str, Any] = {colname: None for colname in ATTRIBUTE_NAMES}
        data.update(
            id=self.id,
            source=self.source,
            source_record=self.source_record,
        )
        for value in self.values:
            colname, py_value = value.to_attribute()
            data[colname] = py_value
        return self.__class__.type_adapter.validate_python(data)
