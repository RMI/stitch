from typing import ClassVar
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

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


class OilAndGasFieldBase(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(use_attribute_docstrings=True)

    name: str | None = Field(min_length=1)
    """Primary name of the resource."""

    country: CountryCodeAlpha3 | None
    """ISO 3166-1 alpha-3 country code."""

    latitude: Latitude | None = None
    """Latitude in WGS84 coordinate system."""

    longitude: Longitude | None = None
    """Longitude in WGS84 coordinate system."""

    last_updated: AwareDatetime | None = None
    """ISO 8601 timestamp of most recent source data update."""

    name_local: str | None = None
    """Name in local script if different from primary name."""

    state_province: str | None = None
    """State or province where the resource is located."""

    region: str | None = None
    """Geographic or administrative region."""

    basin: str | None = None
    """Geological basin name."""

    owners: list[Owner] | None = None
    """List of owners and their ownership stakes."""

    operators: list[Operator] | None = None
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
