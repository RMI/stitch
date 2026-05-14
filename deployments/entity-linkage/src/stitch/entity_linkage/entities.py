from dataclasses import dataclass
from datetime import datetime
from math import ceil
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, computed_field

from stitch.ogsi.model.types import (
    FieldStatus,
    LocationType,
    OGSISrcKey,
    PrimaryHydrocarbonGroup,
    ProductionConventionality,
)


class Timestamped(BaseModel):
    created: datetime = Field(default_factory=datetime.now)
    updated: datetime = Field(default_factory=datetime.now)


class User(BaseModel):
    id: int = Field(...)
    sub: str = Field(...)
    role: str | None = None
    email: EmailStr
    name: str


@dataclass(frozen=True, slots=True)
class RequestAuthContext:
    """
    Request-scoped auth context for inbound request identity.

    not implemented:
    - re-enable downstream relay or OBO auth as an explicit client mode
    - keep user attribution/provenance as separate metadata
    """

    user: User
    bearer_token: str | None


class FieldCandidate(BaseModel):
    id: int
    name: str | None = None
    country: str | None = None

    @computed_field
    @property
    def normalized_name(self) -> str | None:
        if self.name is None:
            return None
        normalized = self.name.strip().casefold()
        return normalized or None


class FieldDetailCandidate(BaseModel):
    id: int
    name: str | None = None
    country: str | None = None


class MatchGroup(BaseModel):
    ids: list[int]
    normalized_name: str
    country: str


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total_count: int
    page: int
    page_size: int

    @computed_field
    @property
    def total_pages(self) -> int:
        return ceil(self.total_count / self.page_size)


SortableField = Literal[
    "name",
    "name_local",
    "basin",
    "state_province",
    "region",
    "id",
    "country",
    "source",
    "field_status",
    "location_type",
    "production_conventionality",
    "primary_hydrocarbon_group",
    "discovery_year",
    "production_start_year",
    "fid_year",
    "latitude",
    "longitude",
]


class OGFieldFilterParams(BaseModel):
    q: str | None = None
    id: int | None = None
    name: str | None = None
    name_local: str | None = None
    basin: str | None = None
    state_province: str | None = None
    region: str | None = None
    country: str | None = None
    field_status: FieldStatus | None = None
    location_type: LocationType | None = None
    production_conventionality: ProductionConventionality | None = None
    primary_hydrocarbon_group: PrimaryHydrocarbonGroup | None = None


class OGFieldSortParams(BaseModel):
    sort_by: SortableField = "name"
    sort_order: Literal["asc", "desc"] = "asc"


class OGFieldQueryParams(PaginationParams, OGFieldFilterParams, OGFieldSortParams):
    source: OGSISrcKey | None = None
