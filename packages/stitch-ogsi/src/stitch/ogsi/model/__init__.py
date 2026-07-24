from typing import Any, Annotated, Final

from pydantic import BaseModel, Field, TypeAdapter, field_validator
from stitch.models import (
    Resource,
    Source,
    SourceView,
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
    "OGFieldSourceView",
    "OGFieldSourceValueView",
    "OGFieldResource",
    "OGFieldResourceView",
    "OGFieldView",
    "LLMSource",
    "LLMSourceView",
    "RMISource",
    "RMISourceView",
    "WoodMacSource",
    "WoodMacSourceView",
    "GemSource",
    "GemSourceView",
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


class GemSourceView(SourceView[int, GEMSrcKey], OilGasFieldBase):
    source: GEMSrcKey = GEM_SRC


class WoodMacSource(Source[int, WMSrcKey], OilGasFieldBase):
    source: WMSrcKey = WM_SRC


class WoodMacSourceView(SourceView[int, WMSrcKey], OilGasFieldBase):
    source: WMSrcKey = WM_SRC


class RMISource(Source[int, RMISrcKey], OilGasFieldBase):
    source: RMISrcKey = RMI_SRC


class RMISourceView(SourceView[int, RMISrcKey], OilGasFieldBase):
    source: RMISrcKey = RMI_SRC


class LLMSource(Source[int, LLMSrcKey], OilGasFieldBase):
    source: LLMSrcKey = LLM_SRC


class LLMSourceView(SourceView[int, LLMSrcKey], OilGasFieldBase):
    source: LLMSrcKey = LLM_SRC


OGFieldSource = Annotated[
    GemSource | WoodMacSource | RMISource | LLMSource,
    Field(discriminator="source"),
]

OGFieldSourceView = Annotated[
    GemSourceView | WoodMacSourceView | RMISourceView | LLMSourceView,
    Field(discriminator="source"),
]

OG_FIELD_SOURCE_VIEW_ADAPTER = TypeAdapter(OGFieldSourceView)


class OGFieldView(OilGasFieldBase):
    id: int


class OGFieldListItemView(BaseModel):
    id: int
    data: OilGasFieldBase
    provenance: dict[str, OGSISrcKey | None] = Field(default_factory=dict)


class OGFieldDetailView(OGFieldListItemView):
    source_data: list[OGFieldSourceView] = Field(default_factory=list)

    @field_validator("source_data", mode="before")
    @classmethod
    def _normalize_source_data(cls, value):
        if not isinstance(value, list):
            return value
        normalized = []
        for item in value:
            normalized.append(OG_FIELD_SOURCE_VIEW_ADAPTER.validate_python(item))
        return normalized


class OGFieldSourceValueView(BaseModel):
    """One source record's value for a single field, with its effective priority.

    Returned by the per-field source-values endpoint, best-first. ``source_id``
    is the id of the source record (distinct from any resource id). ``priority``
    is the effective per-field priority (an override value if the record is
    pinned, otherwise the source's global default). Because overridden records
    always outrank non-overridden ones for a field, ``priority`` is not a total
    order across records -- rely on list order, not on comparing ``priority``
    ints. ``is_override`` marks a record a curator has explicitly re-ranked for
    this field (tier 0); non-override records fall back to the global default.
    """

    source: OGSISrcKey
    source_id: int
    value: Any
    priority: int
    is_override: bool = False


class OGFieldResource(Resource[int, OGFieldSource]):
    provenance: dict[str, tuple[Any, OGSISrcKey, int] | None] = Field(
        default_factory=dict
    )
    view: OilGasFieldBase | None = None


class OGFieldResourceView(Resource[int, OGFieldSourceView]):
    provenance: dict[str, tuple[Any, OGSISrcKey, int] | None] = Field(
        default_factory=dict
    )
    view: OilGasFieldBase | None = None
