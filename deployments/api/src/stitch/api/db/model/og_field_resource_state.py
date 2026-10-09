"""Precomputed, permission-scoped current state of OG field resources (STIT-766).

``og_field_resource_state`` holds one row per ``(resource, permission_mask)``: the
already-coalesced value of every ``OilGasFieldBase`` field as that permission
profile sees it, plus the field -> winning source key ``provenance`` map the list
view returns. ``list`` and ``filter-options`` read these rows instead of re-running
the coalescing window on every request.

This is derived data. Every row is reconstructable from memberships, source values
and priorities using the live coalescer (see ``db.read_model``), so deleting or
emptying the table loses nothing. ``permission_mask`` identifies one of four exact
permission profiles (see ``db.read_model.permissions``).

``og_field_resource_state_status`` is a single-row readiness record. Readers use
the state table only while ``ready`` is true; a missing row means not ready. A
partial, failed, or in-progress rebuild leaves it false, so incomplete state is
never served.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from stitch.api.entities import FILTER_OPTION_FIELDS

from .common import Base
from .oil_gas_field_source_value import ATTRIBUTE_NAMES
from .types import PORTABLE_BIGINT, PORTABLE_FLOAT, PORTABLE_JSON, PORTABLE_JSON_NULL

# Key of the single readiness row in ``og_field_resource_state_status``.
RESOURCE_STATE_STATUS_KEY: Final[str] = "resource_state"


class OGFieldResourceState(Base):
    __tablename__ = "og_field_resource_state"

    resource_id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT,
        ForeignKey("og_field_resources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # One of the exact permission profiles in read_model.permissions.
    permission_mask: Mapped[int] = mapped_column(SmallInteger, primary_key=True)

    # --- Coalesced values, one column per OilGasFieldBase field ---
    # Column types follow ATTRIBUTE_KINDS (text / int / float / json).
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

    # field -> winning source key (or None). Returned with list items; never
    # filtered or sorted on.
    provenance: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "permission_mask BETWEEN 0 AND 3",
            name="ck_resource_state_permission_mask",
        ),
        # Scans of a single profile.
        Index("ix_resource_state_mask_resource", "permission_mask", "resource_id"),
        # The list's default sort (name ASC NULLS LAST, then resource_id).
        Index("ix_resource_state_mask_name", "permission_mask", "name", "resource_id"),
        # filter-options does one DISTINCT per field within a profile.
        *(
            Index(f"ix_resource_state_mask_{field}", "permission_mask", field)
            for field in FILTER_OPTION_FIELDS
        ),
    )


# Fail fast if the value columns drift from the coalesced entity they mirror
# (like the ATTRIBUTE_KINDS guard against OilGasFieldBase). An explicit raise,
# not assert, so the check survives `python -O`.
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


class OGFieldResourceStateStatus(Base):
    """Readiness of ``og_field_resource_state`` (operational metadata, not domain data).

    The migration creates the single row (``key = RESOURCE_STATE_STATUS_KEY``)
    with ``ready = false``. Only a complete full rebuild sets it true.
    """

    __tablename__ = "og_field_resource_state_status"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    ready: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rebuilt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
