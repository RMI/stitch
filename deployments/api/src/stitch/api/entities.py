from math import ceil
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, computed_field

from stitch.ogsi.model import (
    GEM_SRC,
    LLM_SRC,
    RMI_SRC,
    WM_SRC,
    OGFieldDetailView,
    OGFieldSourceValueView,
)
from stitch.ogsi.model.types import (
    FieldStatus,
    LocationType,
    OGSISrcKey,
    PrimaryHydrocarbonGroup,
    ProductionConventionality,
)
from stitch.ogsi.model.og_field import OilGasFieldBase

OGSI_SOURCE_DEFAULT: tuple[OGSISrcKey, ...] = (RMI_SRC, GEM_SRC, WM_SRC, LLM_SRC)


class Timestamped(BaseModel):
    created: datetime = Field(default_factory=datetime.now)
    updated: datetime = Field(default_factory=datetime.now)


# The sources will come in and be initially stored in a raw table.
# That raw table will be an append-only table.
# We'll translate that data into one of the below structures, so each source will have a `UUID` or similar that
# references their id in the "raw" table.
# When pulling into the internal "sources" table, each will get a new unique id which is what the memberships will reference


class User(BaseModel):
    id: int = Field(...)
    sub: str = Field(...)
    role: str | None = None
    email: EmailStr | None = None
    name: str | None = None


class TokenClaimsView(BaseModel):
    sub: str
    email: str | None = None
    name: str | None = None
    permissions: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class AuthMeView(BaseModel):
    user: User | None = None
    claims: TokenClaimsView


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
    "field_status",
    "location_type",
    "production_conventionality",
    "primary_hydrocarbon_group",
    "discovery_year",
    "production_start_year",
    "fid_year",
    "latitude",
    "longitude",
    "resource_id",
]

FilterOptionField = Literal[
    "name",
    "name_local",
    "basin",
    "state_province",
    "region",
    "country",
    "field_status",
    "location_type",
    "production_conventionality",
    "primary_hydrocarbon_group",
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
    source: list[OGSISrcKey] = Field(default_factory=lambda: list(OGSI_SOURCE_DEFAULT))


class OGFieldFilterOptionsParams(BaseModel):
    field: FilterOptionField
    source: list[OGSISrcKey] = Field(default_factory=lambda: list(OGSI_SOURCE_DEFAULT))


class OGFieldFilterOptionsResponse(BaseModel):
    field: FilterOptionField
    values: list[str]


class MergeCandidateStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"


class MergeCandidateCreateRequest(BaseModel):
    resource_ids: list[int] = Field(..., min_length=2)


class MergeCandidateReviewRequest(BaseModel):
    review_notes: str | None = None


class MergeCandidateView(BaseModel):
    id: int
    resource_ids: list[int]
    status: MergeCandidateStatus
    review_notes: str | None = None
    merged_resource_id: int | None = None
    created: datetime
    updated: datetime
    created_by_id: int
    last_updated_by_id: int
    reviewed_at: datetime | None = None
    reviewed_by_id: int | None = None


class FieldComparisonView(BaseModel):
    """One field across a merge candidate, per contributing source.

    ``values`` lists every source (across all candidate resources) that carries a
    value for the field, winner-first (lowest effective ``priority`` wins). The
    merged winner is therefore ``values[0]``.

    ``status`` compares the merge outcome against the baseline -- the first
    resource in the candidate (``resources[0]``), i.e. the resource being merged
    into (``base`` = its coalesced value; ``winner`` = ``values[0].value``):

    - ``new`` -- baseline had no value; the merge introduces one.
    - ``unchanged`` -- ``winner == base`` (a differing source, if any, is lower
      priority and does not win).
    - ``mismatch`` -- ``winner != base``: a higher-priority source overrides the
      baseline's value (the merge changes this field).
    - ``match`` -- every contributing source agrees with the baseline.

    Equality is Python ``==``, which errs toward showing changes (exact float
    equality; ordered ``owners``/``operators`` comparison).

    NOTE: ``values`` (and the derived ``status``) are a client-side best guess at
    what the merge will persist -- they are coalesced in Python from the current
    source data and the default source order. Once coalescing moves entirely into
    the database, the persisted result is authoritative and may differ here.
    """

    field: str
    status: Literal["match", "mismatch", "new", "unchanged"]
    values: list[OGFieldSourceValueView]


class MergeCandidateDetailView(MergeCandidateView):
    resources: list[OGFieldDetailView]
    compare: list[FieldComparisonView]


class OGFieldMergePreviewView(BaseModel):
    resource_ids: list[int]
    data: OilGasFieldBase
    provenance: dict[str, OGSISrcKey | None]
