from collections.abc import Mapping
from typing import Final, Literal
from sqlalchemy.orm import Mapped, mapped_column
from stitch.api.db.model import PORTABLE_BIGINT, Base
from stitch.api.entities import (
    ManualSource,
    SourceKey,
    WMSource,
    CCReservoirsSource as CCSourceEntity,
    GemSource as GemEntity,
)


class SourceBase:
    id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT, primary_key=True, autoincrement=True
    )


class GemSource(SourceBase):
    __tablename__ = "gem_sources"

    def to_entity(self):
        return GemEntity.model_validate(self, from_attributes=True)


class WoodmacSource(SourceBase):
    __tablename__ = "woodmac_sources"

    def to_entity(self):
        return WMSource.model_validate(self, from_attributes=True)


class RMIManualSource(SourceBase):
    __tablename__ = "rmi_manual_sources"
    name_override: Mapped[str | None]
    gwp: Mapped[float | None]
    gor: Mapped[float | None]
    country: Mapped[str | None]
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]

    def to_entity(self):
        return ManualSource.model_validate(self, from_attributes=True)


class CCReservoirsSource(SourceBase):
    __tablename__ = "cc_reservoirs_source"

    def to_entity(self):
        return CCSourceEntity.model_validate(self, from_attributes=True)


SourceModel = GemSource | WoodmacSource | RMIManualSource | CCReservoirsSource
SourceModelCls = type[SourceModel]

SOURCE_TABLES: Final[Mapping[SourceKey, SourceModelCls]] = {
    "gem": GemSource,
    "wm": WoodmacSource,
    "rmi": RMIManualSource,
    "cc": CCReservoirsSource,
}
