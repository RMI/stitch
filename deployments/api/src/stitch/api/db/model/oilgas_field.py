from __future__ import annotations

from typing import Any

from sqlalchemy import Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .common import Base
from .mixins import TimestampMixin, UserAuditMixin

# This is your shared package model (the "base shape")
from deleteme_model_oilgas.field import OilGasFieldBase


class OilGasFieldModel(Base, TimestampMixin, UserAuditMixin):
    __tablename__ = "oil_gas_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Core identifiers
    name: Mapped[str] = mapped_column(String, nullable=False)
    name_local: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Descriptors (mostly optional)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    basin: Mapped[str | None] = mapped_column(String, nullable=True)
    location_type: Mapped[str | None] = mapped_column(String, nullable=True)
    production_conventionality: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    fuel_group: Mapped[str | None] = mapped_column(String, nullable=True)
    operator: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Dates / years (optional)
    discovery_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    production_start_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fid_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Geo (optional)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Status / provenance-ish
    field_status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_updated_source: Mapped[str | None] = mapped_column(String, nullable=True)

    # raw_lineage is `Optional[object]` in your package model :contentReference[oaicite:2]{index=2}
    # Use JSONB in Postgres so you can store dict/list scalars easily.
    raw_lineage: Mapped[Any | None] = mapped_column(JSONB, nullable=True)

    # --- Misc optional fields
    owners: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    reservoir_formation: Mapped[str | None] = mapped_column(String, nullable=True)
    field_depth: Mapped[float | None] = mapped_column(Float, nullable=True)
    subdivision: Mapped[str | None] = mapped_column(String, nullable=True)

    @classmethod
    def from_entity(cls, *, created_by, field: OilGasFieldBase) -> "OilGasFieldModel":
        """
        Build an ORM model from the shared Pydantic model.

        Key behavior:
        - exclude_unset=True: only includes keys the caller actually provided, so
          missing optional fields won't cause constructor errors.
        - nullable columns allow DB rows to persist without those fields.
        """
        data = field.model_dump(exclude_unset=True)

        # Ensure required fields are present (name is required in your Pydantic model).
        # If you later make name optional, you should enforce it here or in API schema.
        model = cls(**data)

        # Your UserAuditMixin uses these columns (based on your earlier SQL).
        model.created_by_id = created_by.id
        model.last_updated_by_id = created_by.id
        return model

    def apply_updates_from_entity(self, *, updated_by, field: OilGasFieldBase) -> None:
        """
        Optional helper for PATCH/PUT later.
        Only updates fields explicitly provided (exclude_unset=True).
        """
        data = field.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(self, k, v)

        self.last_updated_by_id = updated_by.id
