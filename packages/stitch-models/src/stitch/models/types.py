from collections.abc import Mapping, Sequence
from typing import Annotated, Protocol, TypeVar, runtime_checkable

from pydantic import Field
from uuid import UUID

IdType = int | str | UUID

Year = Annotated[int, Field(ge=1800, le=2100)]
Percentage = Annotated[float, Field(ge=0.0, le=100)]
Latitude = Annotated[float, Field(ge=-90.0, le=90.0)]
Longitude = Annotated[float, Field(ge=-180.0, le=180.0)]
CountryCodeAlpha3 = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


@runtime_checkable
class Identified[TId: IdType](Protocol):
    @property
    def id(self) -> TId: ...


@runtime_checkable
class SourceRef[TId: IdType, TSrcKey: str](Identified[TId]):
    @property
    def source(self) -> TSrcKey: ...


ResourceRef = Identified

TId = TypeVar("TId", bound=IdType)
TSk = TypeVar("TSk", bound=str)
TRid = TypeVar("TRid", bound=IdType)
Provenance = Mapping[ResourceRef[TRid], Sequence[SourceRef[TId, TSk]]]


@runtime_checkable
class Provenanced[TResId: IdType, TSrcId: IdType, TSrcKey: str](Protocol):
    @property
    def provenance(self) -> Provenance[TResId, TSrcId, TSrcKey]: ...
