from typing import Any, Annotated, Final

from pydantic import Field, BaseModel
from stitch.models import (
    Resource,
    Source,
)

from stitch.models.types import CountryCodeAlpha3

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
    "LocationType",
    "OilGasOwner",
    "OilGasOperator",
    "OGSISrcKey",
    "OGFieldProvenance",
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


class OGFieldProvenance(BaseModel):
    """Which source "won" for each coalesced field."""

    # Keys are OilGasFieldBase field names, values are the `source` discriminator.
    by_field: dict[str, OGSISrcKey] = Field(default_factory=dict)


class OGFieldResource(Resource[int, OGFieldSource]):
    provenance: dict[str, tuple[OGSISrcKey, int]] = Field(default_factory=dict)


class OGFieldView(OilGasFieldBase):
    id: int
