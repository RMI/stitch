"""Precomputed, permission-scoped current-state read model for OG field resources.

One row per ``(resource, permission_mask)`` holding the fully coalesced value of
every ``OilGasFieldBase`` field, so ``list`` and ``filter-options`` read a stored
answer instead of re-running the coalescing window on every request. This is
derived data: rebuildable at any time from memberships + source values +
priorities (see ``db.read_model.state``) and kept current inside the writing
transaction.

``permission_mask`` encodes the only visibility axes that vary between users --
``wm`` (bit 2) and ``ccr`` (bit 1); every other source is a shared public tier
(see ``db.read_model.permissions`` and the STIT-766 design). A resource therefore
has at most four rows, one per mask. Only unmerged resources are stored; a merge
deletes the merged-away resource's rows.

Value columns mirror ``OilGasFieldBase`` one-for-one (typed, so ``filter-options``
is a plain indexed ``DISTINCT`` and list sort/filter are plain column predicates).
``provenance`` carries the field -> winning source key map the list view exposes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from stitch.api.entities import FILTER_OPTION_FIELDS

from .common import Base
from .oil_gas_field_source_value import ATTRIBUTE_NAMES
from .types import PORTABLE_BIGINT, PORTABLE_FLOAT, PORTABLE_JSON, PORTABLE_JSON_NULL


class OGFieldResourceState(Base):
    __tablename__ = "og_field_resource_state"

    resource_id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT,
        ForeignKey("og_field_resources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Two-bit visibility profile: wm (2) | ccr (1). See read_model.permissions.
    permission_mask: Mapped[int] = mapped_column(SmallInteger, primary_key=True)

    # --- Coalesced value columns, one per OilGasFieldBase field ---
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    name_local: Mapped[str | None] = mapped_column(String, nullable=True)
    state_province: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    basin: Mapped[str | None] = mapped_column(String, nullable=True)
    reservoir_formation: Mapped[str | None] = mapped_column(String, nullable=True)
    location_type: Mapped[str | None] = mapped_column(String, nullable=True)
    production_conventionality: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    primary_hydrocarbon_group: Mapped[str | None] = mapped_column(String, nullable=True)
    field_status: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(PORTABLE_FLOAT, nullable=True)
    longitude: Mapped[float | None] = mapped_column(PORTABLE_FLOAT, nullable=True)
    discovery_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    production_start_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fid_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owners: Mapped[Any | None] = mapped_column(PORTABLE_JSON_NULL, nullable=True)
    operators: Mapped[Any | None] = mapped_column(PORTABLE_JSON_NULL, nullable=True)

    # field -> winning source key (or None); powers the list `provenance` map.
    provenance: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON, nullable=False)

    __table_args__ = tuple(
        # filter-options does one DISTINCT per field within a mask.
        Index(f"ix_og_field_resource_state_{field}", "permission_mask", field)
        for field in FILTER_OPTION_FIELDS
    )


# Fail fast if the value columns drift from the coalesced entity they mirror
# (mirrors the ATTRIBUTE_KINDS guard against OilGasFieldBase). Use an explicit
# raise (not assert) so the check survives `python -O`.
_VALUE_COLUMNS = frozenset(OGFieldResourceState.__table__.columns.keys()) - {
    "resource_id",
    "permission_mask",
    "provenance",
}
if _VALUE_COLUMNS != frozenset(ATTRIBUTE_NAMES):
    raise RuntimeError(
        "OGFieldResourceState value columns out of sync with ATTRIBUTE_NAMES: "
        f"{_VALUE_COLUMNS ^ frozenset(ATTRIBUTE_NAMES)}"
    )
