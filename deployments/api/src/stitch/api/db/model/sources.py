# pyright: reportAssignmentType=false

from collections.abc import Mapping, MutableMapping
from typing import Final, Generic, TypeVar, TypedDict, get_args, get_origin
from pydantic import BaseModel
from sqlalchemy import CheckConstraint, DateTime, Float, Integer, String, inspect
from sqlalchemy.orm import Mapped, mapped_column
from .common import Base
from .types import PORTABLE_BIGINT, PORTABLE_JSON
from stitch.api.entities import (
    IdType,
    SourceKey,
)
from stitch.api.sources import OilAndGasFieldSource
from stitch.resources.ogsi import OilAndGasFieldSourceData


def float_constraint(
    colname: str, min_: float | None = None, max_: float | None = None
) -> CheckConstraint:
    min_str = f"{colname} >= {min_}" if min_ is not None else None
    max_str = f"{colname} <= {max_}" if max_ is not None else None
    expr = " AND ".join(filter(None, (min_str, max_str)))
    return CheckConstraint(expr)


def lat_constraints(colname: str):
    return float_constraint(colname, -90, 90)


def lon_constraints(colname: str):
    return float_constraint(colname, -180, 180)


def year_constraints(colname: str):
    return float_constraint(colname, 1800, 2100)


TModelIn = TypeVar("TModelIn", bound=BaseModel)
TModelOut = TypeVar("TModelOut", bound=BaseModel)


class SourceBase(Base, Generic[TModelIn, TModelOut]):
    __abstract__ = True
    __entity_class_in__: type[TModelIn]
    __entity_class_out__: type[TModelOut]

    id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT, primary_key=True, autoincrement=True
    )

    # All OilAndGasFieldSourceData columns
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String(3), nullable=True)
    latitude: Mapped[float | None] = mapped_column(
        Float, lat_constraints("latitude"), nullable=True
    )
    longitude: Mapped[float | None] = mapped_column(
        Float, lon_constraints("longitude"), nullable=True
    )
    last_updated: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    name_local: Mapped[str | None] = mapped_column(String, nullable=True)
    state_province: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    basin: Mapped[str | None] = mapped_column(String, nullable=True)
    owners: Mapped[list | None] = mapped_column(PORTABLE_JSON, nullable=True)
    operators: Mapped[list | None] = mapped_column(PORTABLE_JSON, nullable=True)
    location_type: Mapped[str | None] = mapped_column(String, nullable=True)
    production_conventionality: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    primary_hydrocarbon_group: Mapped[str | None] = mapped_column(String, nullable=True)
    reservoir_formation: Mapped[str | None] = mapped_column(String, nullable=True)
    discovery_year: Mapped[int | None] = mapped_column(
        Integer, year_constraints("discovery_year"), nullable=True
    )
    production_start_year: Mapped[int | None] = mapped_column(
        Integer, year_constraints("production_start_year"), nullable=True
    )
    fid_year: Mapped[int | None] = mapped_column(
        Integer, year_constraints("fid_year"), nullable=True
    )
    field_status: Mapped[str | None] = mapped_column(String, nullable=True)

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
    def from_entity(cls, entity: TModelIn) -> "SourceBase":
        mapper = inspect(cls)
        column_keys = {col.key for col in mapper.columns}
        filtered = {k: v for k, v in entity.model_dump().items() if k in column_keys}
        return cls(**filtered)


class GemSourceModel(SourceBase[OilAndGasFieldSourceData, OilAndGasFieldSource]):
    __tablename__ = "gem_sources"


class WMSourceModel(SourceBase[OilAndGasFieldSourceData, OilAndGasFieldSource]):
    __tablename__ = "wm_sources"


class RMIManualSourceModel(SourceBase[OilAndGasFieldSourceData, OilAndGasFieldSource]):
    __tablename__ = "rmi_manual_sources"


SourceModel = GemSourceModel | WMSourceModel | RMIManualSourceModel
SourceModelCls = type[SourceModel]

SOURCE_TABLES: Final[Mapping[SourceKey, SourceModelCls]] = {
    "gem": GemSourceModel,
    "wm": WMSourceModel,
    "rmi": RMIManualSourceModel,
}


class SourceModelData(TypedDict, total=False):
    gem: MutableMapping[IdType, GemSourceModel]
    wm: MutableMapping[IdType, WMSourceModel]
    rmi: MutableMapping[IdType, RMIManualSourceModel]


def empty_source_model_data():
    return SourceModelData(gem={}, wm={}, rmi={})
