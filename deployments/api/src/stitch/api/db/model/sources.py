# pyright: reportAssignmentType=false

from collections.abc import Mapping, MutableMapping
from typing import Final, Generic, Self, TypeVar, TypedDict, get_args, get_origin
from pydantic import BaseModel
from sqlalchemy import inspect
from sqlalchemy.orm import Mapped, mapped_column
from .common import Base
from .types import PORTABLE_BIGINT, StitchJson
from stitch.api.entities import (
    CCReservoirsSource,
    GemSource,
    IdType,
    RMIManualSource,
    SourceKey,
    WMData,
    GemData,
    RMIManualData,
    CCReservoirsData,
    WMSource,
)


def float_constraint(
    colname: str, min_: float | None = None, max_: float | None = None
):
    min_str = f"{colname} >= {min_}" if min_ is not None else None
    max_str = f"{colname} <= {max_}" if max_ is not None else None
    return " AND ".join(filter(None, (min_str, max_str)))


def lat_constraints(colname: str):
    return float_constraint(colname, -90, 90)


def lon_constraints(colname: str):
    return float_constraint(colname, -180, 180)


TModelIn = TypeVar("TModelIn", bound=BaseModel)
TModelOut = TypeVar("TModelOut", bound=BaseModel)


class SourceBase(Base, Generic[TModelIn, TModelOut]):
    __abstract__ = True
    __entity_class_in__: type[TModelIn]
    __entity_class_out__: type[TModelOut]

    id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT, primary_key=True, autoincrement=True
    )

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        for base in getattr(cls, "__orig_bases__", ()):
            if get_origin(base) is SourceBase:
                args = get_args(base)
                if len(args) >= 2:
                    if isinstance(args[0], type):
                        cls.__entity_class_in__ = args[0]
                    if isinstance(args[1], type):
                        cls.__entity_class_out__ = args[1]
                break

    def as_entity(self):
        return self.__entity_class_out__.model_validate(self)

    @classmethod
    def from_entity(cls, entity: TModelIn) -> Self:
        mapper = inspect(cls)
        column_keys = {col.key for col in mapper.columns}
        filtered = {k: v for k, v in entity.model_dump().items() if k in column_keys}
        return cls(**filtered)


class GemSourceModel(SourceBase[GemData, GemSource]):
    __tablename__ = "gem_sources"

    name: Mapped[str]
    country: Mapped[str]
    lat: Mapped[float] = mapped_column(lat_constraints("lat"))
    lon: Mapped[float] = mapped_column(lon_constraints("lon"))


class WMSourceModel(SourceBase[WMData, WMSource]):
    __tablename__ = "wm_sources"

    field_name: Mapped[str]
    field_country: Mapped[str]
    production: Mapped[float]


class RMIManualSourceModel(SourceBase[RMIManualData, RMIManualSource]):
    __tablename__ = "rmi_manual_sources"

    name_override: Mapped[str | None]
    gwp: Mapped[float | None]
    gor: Mapped[float | None | None] = mapped_column(
        float_constraint("gor", 0, 1), nullable=True
    )
    country: Mapped[str | None]
    latitude: Mapped[float | None] = mapped_column(
        lat_constraints("latitude"), nullable=True
    )
    longitude: Mapped[float | None] = mapped_column(
        lon_constraints("longitude"), nullable=True
    )


class CCReservoirsDataModel(SourceBase[CCReservoirsData, CCReservoirsSource]):
    __tablename__ = "cc_reservoirs_sources"

    name: Mapped[str]
    basin: Mapped[str]
    depth: Mapped[float]
    geofence: Mapped[list[tuple[float, float]]] = mapped_column(StitchJson())


SourceModel = (
    GemSourceModel | WMSourceModel | RMIManualSourceModel | CCReservoirsDataModel
)
SourceModelCls = type[SourceModel]

SOURCE_TABLES: Final[Mapping[SourceKey, SourceModelCls]] = {
    "gem": GemSourceModel,
    "wm": WMSourceModel,
    "rmi": RMIManualSourceModel,
    "cc": CCReservoirsDataModel,
}


class SourceModelData(TypedDict, total=False):
    gem: MutableMapping[IdType, GemSourceModel]
    wm: MutableMapping[IdType, WMSourceModel]
    cc: MutableMapping[IdType, CCReservoirsDataModel]
    rmi: MutableMapping[IdType, RMIManualSourceModel]


def empty_source_model_data():
    return SourceModelData(gem={}, wm={}, cc={}, rmi={})
