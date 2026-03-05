from __future__ import annotations

from typing import Any, ClassVar

from pydantic import ConfigDict
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stitch.ogsi.model.og_field import OilGasFieldBase

from .common import Base
from .mixins import PayloadMixin, TimestampMixin, UserAuditMixin



def _enum_value(v: Any) -> Any:
    # Works for python Enums (return .value) but leaves strings/None unchanged.
    return getattr(v, "value", v)

class OilGasFieldModel(
    TimestampMixin, UserAuditMixin, PayloadMixin[OilGasFieldBase], Base
):
    """Domain wrapper for an OG field, 1:1 with a Resource."""

    __tablename__ = "oil_gas_fields"

    # Use resource_id as both PK and FK: keeps ids consistent across /resources and /oil_gas_fields
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id"), primary_key=True
    )

    # --- Domain columns (queryable / indexed later if needed) ---
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String(3), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_updated: Mapped[Any | None] = mapped_column(DateTime(timezone=True), nullable=True)
    name_local: Mapped[str | None] = mapped_column(String, nullable=True)
    state_province: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    basin: Mapped[str | None] = mapped_column(String, nullable=True)
    reservoir_formation: Mapped[str | None] = mapped_column(String, nullable=True)
    discovery_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    production_start_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fid_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Store enum-ish fields as strings (decouple DB from enum implementation details).
    location_type: Mapped[str | None] = mapped_column(String, nullable=True)
    production_conventionality: Mapped[str | None] = mapped_column(String, nullable=True)
    primary_hydrocarbon_group: Mapped[str | None] = mapped_column(String, nullable=True)
    field_status: Mapped[str | None] = mapped_column(String, nullable=True)

    # Owners/operators are structured; keep them as jsonb columns.
    owners: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    operators: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    # Raw/original input payload (includes extra fields not in OilGasFieldBase).
    original_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    # Tell PayloadMixin what type to validate/serialize
    payload_type: ClassVar[type[OilGasFieldBase]] = OilGasFieldBase

    # Domain-agnostic: payloads don’t have to have `source`
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    def set_domain(self, domain: OilGasFieldBase) -> None:
        """Populate columns from the validated domain model."""
        self.name = domain.name
        self.country = domain.country
        self.latitude = domain.latitude
        self.longitude = domain.longitude
        self.last_updated = domain.last_updated
        self.name_local = domain.name_local
        self.state_province = domain.state_province
        self.region = domain.region
        self.basin = domain.basin
        self.reservoir_formation = domain.reservoir_formation
        self.discovery_year = domain.discovery_year
        self.production_start_year = domain.production_start_year
        self.fid_year = domain.fid_year
        self.location_type = _enum_value(domain.location_type)
        self.production_conventionality = _enum_value(domain.production_conventionality)
        self.primary_hydrocarbon_group = _enum_value(domain.primary_hydrocarbon_group)
        self.field_status = _enum_value(domain.field_status)
        self.owners = (
            [o.model_dump(mode="json") for o in domain.owners] if domain.owners else None
        )
        self.operators = (
            [o.model_dump(mode="json") for o in domain.operators] if domain.operators else None
        )
