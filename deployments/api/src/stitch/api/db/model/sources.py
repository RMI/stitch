from typing_extensions import Self

from collections.abc import Mapping, MutableMapping
from typing import Final, Generic, TypeVar, TypedDict, get_args, get_origin
from pydantic import BaseModel
from sqlalchemy import CheckConstraint, inspect
from sqlalchemy.orm import Mapped, mapped_column
from .common import Base
from .types import PORTABLE_BIGINT
from stitch.api.entities import (
    IdType,
    SourceKey,
)

from .oil_gas_field_source import OilGasFieldSourceModel

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


SourceModel = (
    OilGasFieldSourceModel
)
SourceModelCls = type[SourceModel]

SOURCE_TABLES: Final[Mapping[SourceKey, SourceModelCls]] = {
    "gem": OilGasFieldSourceModel,
    "wm": OilGasFieldSourceModel,
    "rmi": OilGasFieldSourceModel,
    "llm": OilGasFieldSourceModel,
}


class SourceModelData(TypedDict, total=False):
    og_field: MutableMapping[IdType, OilGasFieldSourceModel]


def empty_source_model_data():
    return SourceModelData(og_field={})
