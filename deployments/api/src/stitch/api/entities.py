from __future__ import annotations
from collections.abc import Sequence
from datetime import datetime
from typing import (
    Annotated,
    Generic,
    Literal,
    Mapping,
    Protocol,
    Self,
    TypeVar,
    runtime_checkable,
)
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field

IdType = int | str | UUID


@runtime_checkable
class HasId(Protocol):
    @property
    def id(self) -> IdType: ...


GEM_SRC = Literal["gem"]
WM_SRC = Literal["wm"]
RMI_SRC = Literal["rmi"]
CC_SRC = Literal["cc"]

SourceKey = GEM_SRC | WM_SRC | RMI_SRC | CC_SRC

TSourceKey = TypeVar("TSourceKey", bound=SourceKey)


class Timestamped(BaseModel):
    created: datetime = Field(default_factory=datetime.now)
    updated: datetime = Field(default_factory=datetime.now)


class Identified(BaseModel):
    id: IdType


class SourceBase(BaseModel, Generic[TSourceKey]):
    source: TSourceKey
    id: IdType


class SourceRef(BaseModel):
    source: SourceKey
    id: int


# The sources will come in and be initially stored in a raw table.
# That raw table will be an append-only table.
# We'll translate that data into one of the below structures, so each source will have a `UUID` or similar that
# references their id in the "raw" table.
# When pulling into the internal "sources" table, each will get a new unique id which is what the memberships will reference


class GemData(BaseModel):
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    country: str


class GemSource(Identified, GemData):
    model_config = ConfigDict(from_attributes=True)


class WMData(BaseModel):
    field_name: str
    field_country: str
    production: float


class WMSource(Identified, WMData):
    model_config = ConfigDict(from_attributes=True)


class RMIManualData(BaseModel):
    name_override: str
    gwp: float
    gor: float = Field(gt=0, lt=1)
    country: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RMIManualSource(Identified, RMIManualData):
    model_config = ConfigDict(from_attributes=True)


class CCReservoirsData(BaseModel):
    name: str
    basin: str
    depth: float
    geofence: Sequence[tuple[float, float]]


class CCReservoirsSource(Identified, CCReservoirsData):
    model_config = ConfigDict(from_attributes=True)


OGSISourcePayload = Annotated[
    GemSource | WMSource | RMIManualSource | CCReservoirsSource,
    Field(discriminator="source"),
]


class SourceData(BaseModel):
    gem: Mapping[IdType, GemSource] = Field(default_factory=dict)
    wm: Mapping[IdType, WMSource] = Field(default_factory=dict)
    rmi: Mapping[IdType, RMIManualSource] = Field(default_factory=dict)
    cc: Mapping[IdType, CCReservoirsSource] = Field(default_factory=dict)


class CreateSourceData(BaseModel):
    gem: Sequence[GemData] = Field(default_factory=list)
    wm: Sequence[WMData] = Field(default_factory=list)
    rmi: Sequence[RMIManualData] = Field(default_factory=list)
    cc: Sequence[CCReservoirsData] = Field(default_factory=list)


class CreateResourceSourceData(BaseModel):
    """Allows for creating source data. We won't have internal ids yet, but the assumption
    is that the data will already be ingested into a "raw" table, thus having a unique id there
    before being transformed and inserted into our internal source table.

    It can be used in isolation to insert source data or used with a new/existing resource to automatically add
    memberships to the resource.
    """

    gem: Sequence[GemSource | int] = Field(default_factory=list)
    wm: Sequence[WMSource | int] = Field(default_factory=list)
    rmi: Sequence[RMIManualSource | int] = Field(default_factory=list)
    cc: Sequence[CCReservoirsSource | int] = Field(default_factory=list)

    def get(self, key: SourceKey):
        if key == "gem":
            return self.gem
        elif key == "wm":
            return self.wm
        elif key == "rmi":
            return self.rmi
        elif key == "cc":
            return self.cc
        raise ValueError(f"Unknown source key: {key}")


class ResourceBase(BaseModel):
    name: str | None = Field(default=None)
    country: str | None = Field(default=None)
    repointed_to: Resource | None = Field(default=None)


class Resource(ResourceBase, Timestamped):
    id: int
    source_data: SourceData
    constituents: Sequence[Self]


class CreateResource(ResourceBase):
    source_data: CreateResourceSourceData | None


class User(BaseModel):
    id: int = Field(...)
    role: str | None = None
    email: EmailStr
    name: str


class SourceSelectionLogic(BaseModel): ...
