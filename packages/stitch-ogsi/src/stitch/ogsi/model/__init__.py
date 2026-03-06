from typing import Any, Annotated, Final

from pydantic import Field
from stitch.models import (
    Resource,
    Source,
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


class OGFieldResource(OilGasFieldBase, Resource[int, OGFieldSource]):
    def to_view(self) -> "OGFieldView":
        """
        Coalesce all source payloads into a single `OGFieldView`.

        Placeholder logic (shape-first):
          - in `source_data` order, fill any still-missing fields with the
            first non-null value found
        """
        if self.id is None:
            raise ValueError("Cannot build OGFieldView from a resource without an id")

        # Start with whatever canonical values may already exist on the resource itself.
        merged: dict[str, Any] = {
            k: getattr(self, k) for k in OilGasFieldBase.model_fields.keys()
        }

        # Fill gaps from sources (first non-null wins).
        for src in self.source_data:
            for k in OilGasFieldBase.model_fields.keys():
                if merged.get(k) is None:
                    v = getattr(src, k, None)
                    if v is not None:
                        merged[k] = v

        return OGFieldView(id=self.id, **merged)


class OGFieldView(OilGasFieldBase):
    id: int
