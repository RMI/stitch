from pydantic import Field
from stitch.resources.ogsi.models import OilAndGasFieldSourceData


class OilAndGasFieldSource(OilAndGasFieldSourceData):
    id: int = Field(..., description="Stable, unique identifier for the resource")
