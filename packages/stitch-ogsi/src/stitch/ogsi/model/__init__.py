from typing import Any, Annotated, Final

from pydantic import Field, BaseModel
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

        def _is_empty(v: Any) -> bool:
            if v is None:
                return True
            if isinstance(v, str) and v.strip() == "":
               return True
            if isinstance(v, (list, tuple, set, dict)) and len(v) == 0:
               return True
            return False

        merged: dict[str, Any] = {}
        prov: dict[str, OGSISrcKey] = {}

        for fname in OilGasFieldBase.model_fields.keys():
            # 1) resource-level value
            cur = getattr(self, fname, None)
            if not _is_empty(cur):
                merged[fname] = cur
                continue

            # 2) first non-empty from sources
            picked = None
            picked_src: OGSISrcKey | None = None
            for src in self.source_data:
                v = getattr(src, fname, None)
                if not _is_empty(v):
                    picked = v
                    picked_src = src.source
                    break

            merged[fname] = picked
            if picked_src is not None:
                prov[fname] = picked_src

        return OGFieldView(
            id=int(self.id) if self.id is not None else 0,
            provenance=OGFieldProvenance(by_field=prov),
            **merged,
        )

class OGFieldView(OilGasFieldBase):
    id: int
    provenance: OGFieldProvenance
