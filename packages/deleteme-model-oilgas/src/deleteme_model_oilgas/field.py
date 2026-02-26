from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class OilGasField(BaseModel):
    """
    Minimal Oil / Gas field domain model.
    """

    model_config = ConfigDict(
        extra="forbid",  # reject unknown fields
        frozen=False,    # allow mutation (change to True if you want immutability)
    )

    name: str = Field(..., min_length=1)
    name_local: Optional[str] = Field(default=None)
    production_start_year: int = Field(..., ge=1800, le=2100)

    latitude: int = Field(..., ge=-90, le=90)
    longitude: int = Field(..., ge=-180, le=180)
