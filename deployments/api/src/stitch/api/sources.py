from pydantic import ConfigDict, Field
from stitch.resources.ogsi.models import OilAndGasFieldSourceData


class OilAndGasFieldSource(OilAndGasFieldSourceData):
    model_config = ConfigDict(from_attributes=True)
    id: int = Field(..., description="Stable, unique identifier for the resource")
