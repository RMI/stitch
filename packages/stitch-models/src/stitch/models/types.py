from typing import Annotated, Protocol, runtime_checkable

from pydantic import Field
from uuid import UUID

IdType = int | str | UUID

Year = Annotated[int, Field(ge=1800, le=2100)]
FractionalPercentage = Annotated[float, Field(ge=0.0, le=100)]
Latitude = Annotated[float, Field(ge=-90.0, le=90.0)]
Longitude = Annotated[float, Field(ge=-180.0, le=180.0)]
CountryCodeAlpha3 = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


@runtime_checkable
class Identified[TId: IdType](Protocol):
    @property
    def id(self) -> TId: ...


@runtime_checkable
class SourceRef[TId: IdType, TSrcKey: str](Identified[TId], Protocol):
    @property
    def source(self) -> TSrcKey: ...


ResourceRef = Identified
