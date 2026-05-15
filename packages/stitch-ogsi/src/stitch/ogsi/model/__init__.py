from typing import Any, Annotated, Final

from pydantic import BaseModel, Field
from stitch.models import (
    Resource,
    Source,
    SourceRecord,
)

from .og_field import OilGasFieldBase, OilGasOwner, OilGasOperator
from .types import (
    GEMSrcKey,
    LLMSrcKey,
    LocationType,
    OGSISrcKey,
    RMISrcKey,
    WMSrcKey,
)

__all__ = [
    "OGFieldSource",
    "OGFieldResource",
    "OGFieldView",
    "LLMSource",
    "RMISource",
    "WoodMacSource",
    "GemSource",
    "SourceRecord",
    "LocationType",
    "OilGasOwner",
    "OilGasOperator",
    "OGSISrcKey",
]


LLM_SRC: Final[LLMSrcKey] = "llm"
GEM_SRC: Final[GEMSrcKey] = "gem"
RMI_SRC: Final[RMISrcKey] = "rmi"
WM_SRC: Final[WMSrcKey] = "wm"


class GemSource(Source[int, GEMSrcKey], OilGasFieldBase):
    source: GEMSrcKey = GEM_SRC


class WoodMacSource(Source[int, WMSrcKey], OilGasFieldBase):
    source: WMSrcKey = WM_SRC


class RMISource(Source[int, RMISrcKey], OilGasFieldBase):
    source: RMISrcKey = RMI_SRC


class LLMSource(Source[int, LLMSrcKey], OilGasFieldBase):
    source: LLMSrcKey = LLM_SRC


OGFieldSource = Annotated[
    GemSource | WoodMacSource | RMISource | LLMSource,
    Field(discriminator="source"),
]


class OGFieldView(OilGasFieldBase):
    id: int


class OGFieldListItemView(BaseModel):
    id: int
    data: OilGasFieldBase
    provenance: dict[str, OGSISrcKey | None] = Field(default_factory=dict)


class OGFieldDetailView(OGFieldListItemView):
    source_data: list[OGFieldSource] = Field(default_factory=list)


class OGFieldResource(Resource[int, OGFieldSource]):
    provenance: dict[str, tuple[Any, OGSISrcKey, int] | None] = Field(
        default_factory=dict
    )
    view: OilGasFieldBase | None = None
