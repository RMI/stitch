from typing import ClassVar, Literal, get_args
from pydantic import BaseModel, ConfigDict, Field

from stitch.models.types import (
    CountryCodeAlpha3,
    Latitude,
    Longitude,
    Year,
    FractionalPercentage,
)

from .types import (
    LocationType,
    ProductionConventionality,
    PrimaryHydrocarbonGroup,
    FieldStatus,
)


class OilGasOwner(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(use_attribute_docstrings=True)

    name: str
    """Name of the company."""

    stake: FractionalPercentage
    """Ownership percentage (0–100)."""


class OilGasOperator(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(use_attribute_docstrings=True)

    name: str
    """Name of the operating company."""

    stake: FractionalPercentage
    """Operating stake percentage (0–100)."""


class OilGasFieldBase(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(use_attribute_docstrings=True)

    name: str | None = Field(min_length=1)
    """Primary name of the resource."""

    country: CountryCodeAlpha3 | None
    """ISO 3166-1 alpha-3 country code."""

    latitude: Latitude | None = None
    """Latitude in WGS84 coordinate system."""

    longitude: Longitude | None = None
    """Longitude in WGS84 coordinate system."""

    name_local: str | None = None
    """Name in local script if different from primary name."""

    state_province: str | None = None
    """State or province where the resource is located."""

    region: str | None = None
    """Geographic or administrative region."""

    basin: str | None = None
    """Geological basin name."""

    owners: list[OilGasOwner] | None = None
    """List of owners and their ownership stakes."""

    operators: list[OilGasOperator] | None = None
    """List of operators and their operating stakes."""

    location_type: LocationType | None = None
    """Whether the resource is onshore or offshore."""

    production_conventionality: ProductionConventionality | None = None
    """Production conventionality classification."""

    primary_hydrocarbon_group: PrimaryHydrocarbonGroup | None = None
    """Primary hydrocarbon type aligned with OGSI nomenclature."""

    reservoir_formation: str | None = None
    """Name or description of the reservoir formation."""

    discovery_year: Year | None = None
    """Year of discovery."""

    production_start_year: Year | None = None
    """Actual or planned year of first production."""

    fid_year: Year | None = None
    """Year of final investment decision."""

    field_status: FieldStatus | None = None
    """Current status of the field."""


# Canonical names of the coalesced ``OilGasFieldBase`` fields, as a Literal so
# API boundaries (path params, request models) validate a field name at the
# schema level -- returning a 422 with the allowed set instead of failing deeper
# in the query layer -- and so the allowed values are self-documenting in the
# OpenAPI spec. Spelled out because a Literal cannot be built dynamically for
# static typing; the runtime check below fails fast if it ever drifts from
# ``OilGasFieldBase`` (mirroring the ``ATTRIBUTE_KINDS`` guard in the API layer).
OGFieldName = Literal[
    "name",
    "country",
    "latitude",
    "longitude",
    "name_local",
    "state_province",
    "region",
    "basin",
    "owners",
    "operators",
    "location_type",
    "production_conventionality",
    "primary_hydrocarbon_group",
    "reservoir_formation",
    "discovery_year",
    "production_start_year",
    "fid_year",
    "field_status",
]

if set(get_args(OGFieldName)) != set(OilGasFieldBase.model_fields):
    raise RuntimeError(
        "OGFieldName out of sync with OilGasFieldBase fields: "
        f"{set(get_args(OGFieldName)) ^ set(OilGasFieldBase.model_fields)}"
    )
