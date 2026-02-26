from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class OilGasFieldBase(BaseModel):
    """
    Minimal Oil / Gas field domain model.
    """

    model_config = ConfigDict(
        extra="forbid",  # reject unknown fields
        frozen=False,    # allow mutation (change to True if you want immutability)
    )
    name: str = Field(..., min_length=1)
    name_local: Optional[str] = Field(default=None)
    country: Optional[str]
    basin: Optional[str] = Field(default=None)
    location_type: Optional[str] = Field(default=None)
    production_conventionality: Optional[str] = Field(default=None)
    fuel_group: Optional[str] = Field(default=None)
    operator: Optional[str] = Field(default=None)
    discovery_year: Optional[int] = Field(default=None)
    production_start_year: Optional[int] = Field(default=None)
    fid_year: Optional[int] = Field(default=None)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    field_status: Optional[str]
    last_updated_source: Optional[str] = Field(default=None)
    raw_lineage: Optional[object] = Field(default=None)
    owners: Optional[str]
    region: Optional[str]
    reservoir_formation: Optional[str]
    field_depth: Optional[float] = Field(default=None)
    subdivision: Optional[str] = Field(default = None)
