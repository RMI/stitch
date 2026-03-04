from collections.abc import Sequence
from typing import Annotated, Final

from pydantic import Field
from stitch.models import (
    Resource,
    Source,
    SourcePayload,
)

from .og_field import OilGasFieldBase, OilGasOwner, OilGasOperator
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
    "OilGasOwner",
    "OilGasOperator",
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


class OGSourcePayload(SourcePayload):
    gem: Sequence[GemSource] = Field(default_factory=lambda: [])
    wm: Sequence[WoodMacSource] = Field(default_factory=lambda: [])
    rmi: Sequence[RMISource] = Field(default_factory=lambda: [])
    llm: Sequence[LLMSource] = Field(default_factory=lambda: [])


class OGFieldResource(OilGasFieldBase, Resource[int, OGSourcePayload]): ...


class OGFieldView(OilGasFieldBase):
    id: int
