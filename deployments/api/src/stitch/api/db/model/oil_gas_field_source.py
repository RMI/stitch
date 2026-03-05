from __future__ import annotations

from typing import Any

from sqlalchemy import (
    Integer,
    String,
    JSON,
    Column,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column

from stitch.ogsi.model.og_field import OilGasFieldBase

from .common import Base
from .mixins import TimestampMixin, UserAuditMixin


class OilGasFieldSourceModel(TimestampMixin, UserAuditMixin, Base):
    """A single OG field source record (canonicalized), feedable into a Resource."""

    __tablename__ = "oil_gas_field_source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    source: Mapped[str | None] = mapped_column(String, nullable=True)

    # Flat domain columns for filtering, indexing, query, etc.
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    basin: Mapped[str | None] = mapped_column(String, nullable=True)

    # full normalized domain payload
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # original raw payload as given by client
    original_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # optionally track an external ref if useful
    source_ref: Mapped[str | None] = mapped_column(String, nullable=True)
