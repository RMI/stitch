from typing import Any, Annotated, Final

from pydantic import BaseModel, Field, TypeAdapter, field_validator
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
    "OGFieldSourceView",
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


class GemSourceView(OilGasFieldBase):
    id: int | None = None
    source: GEMSrcKey = GEM_SRC


class WoodMacSource(Source[int, WMSrcKey], OilGasFieldBase):
    source: WMSrcKey = WM_SRC


class WoodMacSourceView(OilGasFieldBase):
    id: int | None = None
    source: WMSrcKey = WM_SRC


class RMISource(Source[int, RMISrcKey], OilGasFieldBase):
    source: RMISrcKey = RMI_SRC


class RMISourceView(OilGasFieldBase):
    id: int | None = None
    source: RMISrcKey = RMI_SRC


class LLMSource(Source[int, LLMSrcKey], OilGasFieldBase):
    source: LLMSrcKey = LLM_SRC


class LLMSourceView(OilGasFieldBase):
    id: int | None = None
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
            if isinstance(item, BaseModel):
                normalized.append(
                    OG_FIELD_SOURCE_VIEW_ADAPTER.validate_python(
                        item.model_dump(exclude={"source_record"})
                    )
                )
            else:
                normalized.append(OG_FIELD_SOURCE_VIEW_ADAPTER.validate_python(item))
        return normalized


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
