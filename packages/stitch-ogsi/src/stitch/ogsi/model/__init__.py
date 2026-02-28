from collections.abc import Mapping, Sequence
from typing import Annotated, Final

from pydantic import Field
from stitch.models import (
    Resource,
    Source,
    SourcePayload,
)

from .og_field import OilAndGasFieldBase, Owner, Operator
from .types import (
    FieldStatus,
    GEMSrcKey,
    LLMSrcKey,
    LocationType,
    OGSISrcKey,
    PrimaryHydrocarbonGroup,
    ProductionConventionality,
    RMISrcKey,
    WMSrcKey,
)

__all__ = [
    "OilAndGasFieldSource",
    "LLMSource",
    "RMISource",
    "WoodMacSource",
    "GemSource",
    "ProductionConventionality",
    "PrimaryHydrocarbonGroup",
    "LocationType",
    "FieldStatus",
    "Owner",
    "Operator",
]


LLM_SRC: Final[LLMSrcKey] = "llm"
GEM_SRC: Final[GEMSrcKey] = "gem"
RMI_SRC: Final[RMISrcKey] = "rmi"
WM_SRC: Final[WMSrcKey] = "wm"


class GemSource(Source[int, GEMSrcKey], OilAndGasFieldBase):
    source = GEM_SRC


class WoodMacSource(Source[int, WMSrcKey], OilAndGasFieldBase):
    source = WM_SRC


class RMISource(Source[int, RMISrcKey], OilAndGasFieldBase):
    source = RMI_SRC


class LLMSource(Source[int, LLMSrcKey], OilAndGasFieldBase):
    source = LLM_SRC


OilAndGasFieldSource = Annotated[
    GemSource | WoodMacSource | RMISource | LLMSource,
    Field(discriminator="source"),
]


class OGSourcePayload(SourcePayload):
    gem: Sequence[GemSource] = Field(default_factory=list)
    wm: Sequence[WoodMacSource] = Field(default_factory=list)
    rmi: Sequence[RMISource] = Field(default_factory=list)
    cc: Sequence[LLMSource] = Field(default_factory=list)


class OGFieldResource(
    OilAndGasFieldBase, Resource[int, int, OGSISrcKey, SourcePayload]
): ...


class OilAndGasFieldView(OilAndGasFieldBase):
    id: int
