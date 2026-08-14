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


def normalize_name(name: str | None) -> str | None:
    """Blocking key for name matching: case-insensitive, whitespace-trimmed."""
    if name is None:
        return None
    normalized = name.strip().casefold()
    return normalized or None


def normalize_country(country: str | None) -> str | None:
    """Country confirmation key: whitespace-trimmed, upper-cased."""
    if country is None:
        return None
    normalized = country.strip().upper()
    return normalized or None


class FieldCandidate(BaseModel):
    id: int
    name: str | None = None
    country: str | None = None

    @computed_field
    @property
    def normalized_name(self) -> str | None:
        return normalize_name(self.name)


class FieldDetailCandidate(BaseModel):
    id: int
    name: str | None = None
    country: str | None = None


def user_label(user: User) -> str:
    return user.name or user.email or user.sub


class ResourceLinkResult(BaseModel):
    """Outcome of linking a single resource against its duplicates."""

    resource_id: int
    matched_ids: list[int]
    merge_candidate_created: bool
    skipped_existing: bool


class LinkProgress(BaseModel):
    """Live counters for an in-flight pass, mutated in place by ``link_all``.

    Held by the job record so a poll of the status endpoint reports how far the
    run has got -- including on a run that ultimately fails, where the counters
    are the only record of what it managed to do.
    """

    resources_scanned: int = 0
    match_groups_found: int = 0
    merge_candidates_created: int = 0
    merge_candidates_skipped: int = 0
    last_resource_id: int | None = None


class BulkLinkResponse(BaseModel):
    """Summary of a full linkage pass over every resource."""

    initiated_by: str
    apply_merges: bool
    resources_scanned: int
    match_groups: list[list[int]]
    merge_candidates_created: int
    merge_candidates_skipped: int


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
