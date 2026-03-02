from collections.abc import Sequence
from typing import Annotated, Final

from pydantic import Field
from stitch.models import (
    Resource,
    Source,
    SourcePayload,
)

from .og_field import OilAndGasFieldBase, Owner, Operator
from .types import (
    GEMSrcKey,
    LLMSrcKey,
    LocationType,
    RMISrcKey,
    WMSrcKey,
)

__all__ = [
    "OGFieldSource",
    "OGSourcePayload",
    "OGFieldResource",
    "OGFieldView",
    "LLMSource",
    "RMISource",
    "WoodMacSource",
    "GemSource",
    "LocationType",
    "Owner",
    "Operator",
]


LLM_SRC: Final[LLMSrcKey] = "llm"
GEM_SRC: Final[GEMSrcKey] = "gem"
RMI_SRC: Final[RMISrcKey] = "rmi"
WM_SRC: Final[WMSrcKey] = "wm"


class GemSource(Source[int, GEMSrcKey], OilAndGasFieldBase):
    source: GEMSrcKey = GEM_SRC


class WoodMacSource(Source[int, WMSrcKey], OilAndGasFieldBase):
    source: WMSrcKey = WM_SRC


class RMISource(Source[int, RMISrcKey], OilAndGasFieldBase):
    source: RMISrcKey = RMI_SRC


class LLMSource(Source[int, LLMSrcKey], OilAndGasFieldBase):
    source: LLMSrcKey = LLM_SRC


OGFieldSource = Annotated[
    GemSource | WoodMacSource | RMISource | LLMSource,
    Field(discriminator="source"),
]


class OGSourcePayload(SourcePayload):
    gem: Sequence[GemSource] = Field(default_factory=lambda: [])
    wm: Sequence[WoodMacSource] = Field(default_factory=lambda: [])
    rmi: Sequence[RMISource] = Field(default_factory=lambda: [])
    cc: Sequence[LLMSource] = Field(default_factory=lambda: [])


class OGFieldResource(OilAndGasFieldBase, Resource[int, SourcePayload]): ...


class OGFieldView(OilAndGasFieldBase):
    id: int
