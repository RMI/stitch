from typing import Annotated

from pydantic import BaseModel, Field
from uuid import UUID

IdType = int | str | UUID

Year = Annotated[int, Field(ge=1800, le=2100)]
Percentage = Annotated[float, Field(ge=0.0, le=100)]
Latitude = Annotated[float, Field(ge=-90.0, le=90.0)]
Longitude = Annotated[float, Field(ge=-180.0, le=180.0)]
CountryCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class Identified(BaseModel):
    id: IdType
