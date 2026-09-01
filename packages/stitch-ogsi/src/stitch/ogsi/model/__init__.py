from typing import Any, Annotated, Final

from pydantic import BaseModel, Field, TypeAdapter, field_validator
from stitch.models import (
    Resource,
    Source,
    SourceView,
    SourceRecord,
)

from .og_field import OGFieldName, OilGasFieldBase, OilGasOwner, OilGasOperator
from .types import (
    ALBSrcKey,
    BCSrcKey,
    CCRSrcKey,
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
    "CCRSource",
    "CCRSourceView",
    "ALBSource",
    "ALBSourceView",
    "BCSource",
    "BCSourceView",
    "SourceRecord",
    "LocationType",
    "OGFieldName",
    "OilGasOwner",
    "OilGasOperator",
    "OGSISrcKey",
    "SOURCE_PRIORITY",
]


LLM_SRC: Final[LLMSrcKey] = "llm"
GEM_SRC: Final[GEMSrcKey] = "gem"
RMI_SRC: Final[RMISrcKey] = "rmi"
WM_SRC: Final[WMSrcKey] = "wm"
CCR_SRC: Final[CCRSrcKey] = "ccr"
ALB_SRC: Final[ALBSrcKey] = "alb"
BC_SRC: Final[BCSrcKey] = "bc"

# Canonical source coalescing priority (highest first). Single source of truth
# for the coalescer, the query-param default, and the DB seed.
SOURCE_PRIORITY: Final[tuple[OGSISrcKey, ...]] = (
    RMI_SRC,
    WM_SRC,
    CCR_SRC,
    BC_SRC,
    ALB_SRC,
    GEM_SRC,
    LLM_SRC,
)


class GemSource(Source[int, GEMSrcKey], OilGasFieldBase):
    source: GEMSrcKey = GEM_SRC


class GemSourceView(SourceView[int, GEMSrcKey], OilGasFieldBase):
    source: GEMSrcKey = GEM_SRC


class CCRSource(Source[int, CCRSrcKey], OilGasFieldBase):
    source: CCRSrcKey = CCR_SRC


class CCRSourceView(SourceView[int, CCRSrcKey], OilGasFieldBase):
    source: CCRSrcKey = CCR_SRC


class ALBSource(Source[int, ALBSrcKey], OilGasFieldBase):
    source: ALBSrcKey = ALB_SRC


class ALBSourceView(SourceView[int, ALBSrcKey], OilGasFieldBase):
    source: ALBSrcKey = ALB_SRC


class BCSource(Source[int, BCSrcKey], OilGasFieldBase):
    source: BCSrcKey = BC_SRC


class BCSourceView(SourceView[int, BCSrcKey], OilGasFieldBase):
    source: BCSrcKey = BC_SRC


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
    GemSource
    | WoodMacSource
    | RMISource
    | LLMSource
    | CCRSource
    | ALBSource
    | BCSource,
    Field(discriminator="source"),
]

OGFieldSourceView = Annotated[
    GemSourceView
    | WoodMacSourceView
    | RMISourceView
    | LLMSourceView
    | CCRSourceView
    | ALBSourceView
    | BCSourceView,
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
    """One source's value for a single field, in effective priority order.

    Returned by the per-field source-values endpoint, winner-first. ``source_id``
    is the id of the source record (distinct from any resource id). ``priority``
    is the row's 0-based rank in that order (0 = coalesced winner); it is a rank
    *position*, not the stored priority number, because per-field tiering means
    the raw numbers are no longer a single cross-record total order. **Consumers
    rely on list order**, which is authoritative. ``is_override`` marks a row a
    curator has explicitly re-ranked for this field (tier 0); non-override rows
    (tier 1) fall back to the global default priority and rank below every
    curated row.
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
