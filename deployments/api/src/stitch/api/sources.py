from __future__ import annotations
from pydantic import AwareDatetime, BaseModel, Field, confloat, conint, constr
from enum import Enum
from typing import Any, Literal


class Owner(BaseModel):
    name: str = Field(..., description="Name of the company")
    stake: float = Field(
        ..., description="Ownership percentage (0-100)", ge=0.0, le=100
    )


class Operator(BaseModel):
    name: str = Field(..., description="Name of the operating company")
    stake: float = Field(
        ..., description="Operating stake percentage (0-100)", ge=0.0, le=100
    )


class LocationType(Enum):
    Onshore = "Onshore"
    Offshore = "Offshore"
    Unknown = "Unknown"


LocationType_ = Literal["Onshore", "Offshore", "Unknown"]


class ProductionConventionality(Enum):
    Conventional = "Conventional"
    Unconventional = "Unconventional"
    Mixed = "Mixed"
    Unknown = "Unknown"


class PrimaryHydrocarbonGroup(Enum):
    Ultra_Light_Oil = "Ultra-Light Oil"
    Light_Oil = "Light Oil"
    Medium_Oil = "Medium Oil"
    Heavy_Oil = "Heavy Oil"
    Extra_Heavy_Oil = "Extra-Heavy Oil"
    Dry_Gas = "Dry Gas"
    Wet_Gas = "Wet Gas"
    Acid_Gas = "Acid Gas"
    Condensate = "Condensate"
    Mixed = "Mixed"
    Unknown = "Unknown"


class FieldStatus(Enum):
    Producing = "Producing"
    Non_Producing = "Non-Producing"
    Abandoned = "Abandoned"
    Planned = "Planned"


class RawLineage(BaseModel):
    gem: dict[str, dict[str, Any]] | None = None
    woodmac: dict[str, dict[str, Any]] | None = None


class Schema(BaseModel):
    id: int = Field(..., description="Stable, unique identifier for the resource")
    repointed_to: str | None = Field(
        None,
        description="If this resource has been repointed, the `id` of the new resource",
    )
    name: str | None = Field(
        ..., description="Primary name of the resource", min_length=1
    )
    country: str | None = Field(
        ..., description="ISO 3166-1 alpha-3 country code", pattern=r"^[A-Z]{3}$"
    )
    latitude: float | None = Field(
        None, description="Latitude in WGS84 coordinate system", ge=-90.0, le=90
    )
    longitude: float | None = Field(
        None, description="Longitude in WGS84 coordinate system", ge=-180.0, le=180.0
    )
    last_updated: AwareDatetime | None = Field(
        None, description="ISO 8601 timestamp of most recent source data update"
    )


class OilAndGasFieldSource(Schema):
    name_local: str | None = Field(
        None, description="Name in local script if different from primary name"
    )
    state_province: str | None = Field(
        None, description="State or province where the resource is located"
    )
    region: str | None = Field(None, description="Geographic or administrative region")
    basin: str | None = Field(None, description="Geological basin name")
    owners: list[Owner] | None = Field(
        None, description="List of owners and their ownership stakes"
    )
    operators: list[Operator] | None = Field(
        None, description="List of operators and their operating stakes"
    )
    location_type: LocationType | None = Field(
        None, description="Whether the resource is onshore or offshore"
    )
    production_conventionality: ProductionConventionality | None = Field(
        None, description="Production conventionality classification"
    )
    primary_hydrocarbon_group: PrimaryHydrocarbonGroup | None = Field(
        None, description="Primary hydrocarbon type aligned with OGSI nomenclature"
    )
    reservoir_formation: str | None = Field(
        None, description="Name or description of the reservoir formation"
    )
    discovery_year: int | None = Field(
        None, description="Year of discovery", ge=1800, le=2100
    )
    production_start_year: int | None = Field(
        None, description="Actual or planned year of first production", ge=1800, le=2100
    )
    fid_year: int | None = Field(
        None, description="Year of final investment decision (FID)", ge=1800, le=2100
    )
    field_status: FieldStatus | None = Field(
        None, description="Current status of the field"
    )
