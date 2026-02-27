from collections.abc import Mapping, Sequence
from typing import Annotated, Final

from pydantic import Field
from stitch.models import (
    ManagedResource,
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


class GemSource(Source[GEMSrcKey], OilAndGasFieldBase):
    source = GEM_SRC


class WoodMacSource(Source[WMSrcKey], OilAndGasFieldBase):
    source = WM_SRC


class RMISource(Source[RMISrcKey], OilAndGasFieldBase):
    source = RMI_SRC


class LLMSource(Source[LLMSrcKey], OilAndGasFieldBase):
    source = LLM_SRC


class ManagedGemSource(GemSource):
    id: int


class ManagedWoodMacSource(WoodMacSource):
    id: int


class ManagedRMISource(RMISource):
    id: int


class ManagedLLMSource(LLMSource):
    id: int


OilAndGasFieldSource = Annotated[
    GemSource | WoodMacSource | RMISource | LLMSource,
    Field(discriminator="source"),
]


class OGSourcePayload(SourcePayload):
    gem: Sequence[GemSource] = Field(default_factory=list)
    wm: Sequence[WoodMacSource] = Field(default_factory=list)
    rmi: Sequence[RMISource] = Field(default_factory=list)
    cc: Sequence[LLMSource] = Field(default_factory=list)


class OGManagedSourcePayload(SourcePayload):
    gem: Mapping[int, ManagedGemSource] = Field(default_factory=dict)
    wm: Mapping[int, ManagedWoodMacSource] = Field(default_factory=dict)
    rmi: Mapping[int, ManagedRMISource] = Field(default_factory=dict)
    cc: Mapping[int, ManagedLLMSource] = Field(default_factory=dict)


class OGFieldResource(OilAndGasFieldBase, Resource[SourcePayload]): ...


class ManagedOGFieldResource(
    OilAndGasFieldBase, ManagedResource[int, int, OGSISrcKey, OGManagedSourcePayload]
): ...
