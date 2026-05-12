from datetime import datetime
from typing import Any, Annotated, Final, Literal

from pydantic import BaseModel, Field, JsonValue
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
    "OGFieldSourceCreate",
    "OGFieldSourceDetail",
    "OGFieldResourceCreate",
    "OGFieldResource",
    "OGFieldView",
    "LLMSource",
    "LLMSourceCreate",
    "LLMSourceDetail",
    "RMISource",
    "RMISourceCreate",
    "RMISourceDetail",
    "SourceRecord",
    "WoodMacSource",
    "WoodMacSourceCreate",
    "WoodMacSourceDetail",
    "GemSource",
    "GemSourceCreate",
    "GemSourceDetail",
    "LocationType",
    "OilGasOwner",
    "OilGasOperator",
    "OGSISrcKey",
]


LLM_SRC: Final[LLMSrcKey] = "llm"
GEM_SRC: Final[GEMSrcKey] = "gem"
RMI_SRC: Final[RMISrcKey] = "rmi"
WM_SRC: Final[WMSrcKey] = "wm"


class SourceRecord(BaseModel):
    kind: Literal["provider", "seed_static", "seed_faker", "llm_audit"]
    record_id: str | None = None
    run_id: str | None = None
    observed_at: datetime
    producer: str
    payload: JsonValue


class GemSource(Source[int, GEMSrcKey], OilGasFieldBase):
    source: GEMSrcKey = GEM_SRC


class WoodMacSource(Source[int, WMSrcKey], OilGasFieldBase):
    source: WMSrcKey = WM_SRC


class RMISource(Source[int, RMISrcKey], OilGasFieldBase):
    source: RMISrcKey = RMI_SRC


class LLMSource(Source[int, LLMSrcKey], OilGasFieldBase):
    source: LLMSrcKey = LLM_SRC


class GemSourceCreate(GemSource):
    source_record: SourceRecord


class WoodMacSourceCreate(WoodMacSource):
    source_record: SourceRecord


class RMISourceCreate(RMISource):
    source_record: SourceRecord


class LLMSourceCreate(LLMSource):
    source_record: SourceRecord


class GemSourceDetail(GemSourceCreate):
    source_record_hash: str


class WoodMacSourceDetail(WoodMacSourceCreate):
    source_record_hash: str


class RMISourceDetail(RMISourceCreate):
    source_record_hash: str


class LLMSourceDetail(LLMSourceCreate):
    source_record_hash: str


OGFieldSource = Annotated[
    GemSource | WoodMacSource | RMISource | LLMSource,
    Field(discriminator="source"),
]

OGFieldSourceCreate = Annotated[
    GemSourceCreate | WoodMacSourceCreate | RMISourceCreate | LLMSourceCreate,
    Field(discriminator="source"),
]

OGFieldSourceDetail = Annotated[
    GemSourceDetail | WoodMacSourceDetail | RMISourceDetail | LLMSourceDetail,
    Field(discriminator="source"),
]


class OGFieldView(OilGasFieldBase):
    id: int


class OGFieldListItemView(BaseModel):
    id: int
    data: OilGasFieldBase
    provenance: dict[str, OGSISrcKey | None] = Field(default_factory=dict)


class OGFieldDetailView(OGFieldListItemView):
    source_data: list[OGFieldSource] = Field(default_factory=list)


class OGFieldResource(Resource[int, OGFieldSource]):
    provenance: dict[str, tuple[Any, OGSISrcKey, int] | None] = Field(
        default_factory=dict
    )
    view: OilGasFieldBase | None = None


class OGFieldResourceCreate(Resource[int, OGFieldSourceCreate]):
    provenance: dict[str, tuple[Any, OGSISrcKey, int] | None] = Field(
        default_factory=dict
    )
    view: OilGasFieldBase | None = None
