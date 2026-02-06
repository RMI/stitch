from collections.abc import Sequence
from datetime import datetime
from typing import (
    Generic,
    Literal,
    Mapping,
    Protocol,
    TypeVar,
    runtime_checkable,
)
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

from stitch.resources.ogsi.models import OilAndGasFieldSourceData
from stitch.api.sources import OilAndGasFieldSource

IdType = int | str | UUID


@runtime_checkable
class HasId(Protocol):
    @property
    def id(self) -> IdType: ...


GEM_SRC = Literal["gem"]
WM_SRC = Literal["wm"]
RMI_SRC = Literal["rmi"]

SourceKey = GEM_SRC | WM_SRC | RMI_SRC

TSourceKey = TypeVar("TSourceKey", bound=SourceKey)


class Timestamped(BaseModel):
    created: datetime = Field(default_factory=datetime.now)
    updated: datetime = Field(default_factory=datetime.now)


class SourceBase(BaseModel, Generic[TSourceKey]):
    source: TSourceKey
    id: IdType


class SourceRef(BaseModel):
    source: SourceKey
    id: int


# Entity aliases — all sources share the same schema
GemData = OilAndGasFieldSourceData
WMData = OilAndGasFieldSourceData
RMIManualData = OilAndGasFieldSourceData
GemSource = OilAndGasFieldSource
WMSource = OilAndGasFieldSource
RMIManualSource = OilAndGasFieldSource


class SourceData(BaseModel):
    gem: Mapping[IdType, GemSource] = Field(default_factory=dict)
    wm: Mapping[IdType, WMSource] = Field(default_factory=dict)
    rmi: Mapping[IdType, RMIManualSource] = Field(default_factory=dict)


class CreateSourceData(BaseModel):
    gem: Sequence[GemData] = Field(default_factory=list)
    wm: Sequence[WMData] = Field(default_factory=list)
    rmi: Sequence[RMIManualData] = Field(default_factory=list)


class CreateResourceSourceData(BaseModel):
    """Allows for creating source data or referencing existing sources by ID.

    It can be used in isolation to insert source data or used with a new/existing resource to automatically add
    memberships to the resource.
    """

    gem: Sequence[GemData | int] = Field(default_factory=list)
    wm: Sequence[WMData | int] = Field(default_factory=list)
    rmi: Sequence[RMIManualData | int] = Field(default_factory=list)

    def get(self, key: SourceKey):
        if key == "gem":
            return self.gem
        elif key == "wm":
            return self.wm
        elif key == "rmi":
            return self.rmi
        raise ValueError(f"Unknown source key: {key}")


class ResourceBase(BaseModel):
    name: str | None = Field(default=None)
    country: str | None = Field(default=None)
    repointed_to: "Resource | None" = Field(default=None)


class Resource(ResourceBase, Timestamped):
    id: int
    source_data: SourceData
    constituents: Sequence["Resource"]


class CreateResource(ResourceBase):
    source_data: CreateResourceSourceData | None


class User(BaseModel):
    id: int = Field(...)
    role: str | None = None
    email: EmailStr
    name: str


class SourceSelectionLogic(BaseModel): ...
