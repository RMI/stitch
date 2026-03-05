from collections.abc import Sequence
from datetime import datetime
from typing import (
    Generic,
    Mapping,
    Protocol,
    TypeVar,
    runtime_checkable,
)
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

from stitch.ogsi.model.types import OGSISrcKey
from stitch.ogsi.model.og_field import OilGasFieldBase

IdType = int | str | UUID


@runtime_checkable
class HasId(Protocol):
    @property
    def id(self) -> IdType: ...


TSourceKey = TypeVar("TSourceKey", bound=OGSISrcKey)


class Timestamped(BaseModel):
    created: datetime = Field(default_factory=datetime.now)
    updated: datetime = Field(default_factory=datetime.now)


class Identified(BaseModel):
    id: IdType


class SourceBase(BaseModel, Generic[TSourceKey]):
    source: TSourceKey
    id: IdType


class SourceRef(BaseModel):
    source: OGSISrcKey
    id: int


# The sources will come in and be initially stored in a raw table.
# That raw table will be an append-only table.
# We'll translate that data into one of the below structures, so each source will have a `UUID` or similar that
# references their id in the "raw" table.
# When pulling into the internal "sources" table, each will get a new unique id which is what the memberships will reference


class SourceData(BaseModel):
    og_field: Mapping[IdType, OilGasFieldBase] = Field(default_factory=dict)


class CreateSourceData(BaseModel):
    og_field: Sequence[OilGasFieldBase] = Field(default_factory=list)


class CreateResourceSourceData(BaseModel):
    """Allows for creating source data or referencing existing sources by ID.

    It can be used in isolation to insert source data or used with a new/existing resource to automatically add
    memberships to the resource.
    """

    og_field: Sequence[OilGasFieldBase | int] = Field(default_factory=list)

    def get(self, key: OGSISrcKey):
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
    sub: str = Field(...)
    role: str | None = None
    email: EmailStr
    name: str


class SourceSelectionLogic(BaseModel): ...
