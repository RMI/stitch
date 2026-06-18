from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from stitch.ogsi.model.og_field import OilGasFieldBase

from .common import Base
from .types import PORTABLE_BIGINT, PORTABLE_JSON, PORTABLE_REAL


# Field → value-column routing constants (single source of truth)
VALUE_TEXT_FIELDS = (
    "name",
    "country",
    "name_local",
    "state_province",
    "region",
    "basin",
    "reservoir_formation",
    "location_type",
    "production_conventionality",
    "primary_hydrocarbon_group",
    "field_status",
)
VALUE_NUM_FIELDS = (
    "latitude",
    "longitude",
    "discovery_year",
    "production_start_year",
    "fid_year",
)
VALUE_JSON_FIELDS = ("owners", "operators")

FIELD_TO_VALUE_COLUMN: dict[str, str] = {
    **{f: "value_text" for f in VALUE_TEXT_FIELDS},
    **{f: "value_num" for f in VALUE_NUM_FIELDS},
    **{f: "value_json" for f in VALUE_JSON_FIELDS},
}

# Verify at import time that routing constants cover all OilGasFieldBase fields exactly
_all_routed = set(FIELD_TO_VALUE_COLUMN)
_model_fields = set(OilGasFieldBase.model_fields)
assert _all_routed == _model_fields, (
    f"FIELD_TO_VALUE_COLUMN mismatch. "
    f"Missing: {_model_fields - _all_routed}. Extra: {_all_routed - _model_fields}."
)


class OGFieldResourceQueryView(Base):
    """Precomputed EAV projection table: one row per (resource_id, source_id, column_name)."""

    __tablename__ = "og_field_resource_query_view"

    __table_args__ = (
        Index("ix_qv_colname_text", "column_name", "source", "value_text"),
        Index("ix_qv_colname_num", "column_name", "source", "value_num"),
    )

    resource_id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT, ForeignKey("og_field_resources.id"), primary_key=True
    )
    source_id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT, ForeignKey("oil_gas_field_sources.id"), primary_key=True
    )
    column_name: Mapped[str] = mapped_column(String(40), primary_key=True)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    value_text: Mapped[str | None] = mapped_column(String, nullable=True)
    value_num: Mapped[float | None] = mapped_column(PORTABLE_REAL, nullable=True)
    value_json: Mapped[list | None] = mapped_column(PORTABLE_JSON, nullable=True)
