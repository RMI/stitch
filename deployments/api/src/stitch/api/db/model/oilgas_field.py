from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

# IMPORTANT:
# Adjust these imports to match your repo's actual base/mixins.
# From your tree, you likely have something like common.py / mixins.py already.
from .common import Base  # <- change if your Base lives elsewhere
from .mixins import TimestampMixin, UserAuditMixin


class OilGasFieldModel(Base, TimestampMixin, UserAuditMixin):
    __tablename__ = "oil_gas_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String, nullable=False)
    name_local: Mapped[str | None] = mapped_column(String, nullable=True)

    production_start_year: Mapped[int] = mapped_column(Integer, nullable=False)

    # ints with constraints enforced at API level; DB constraints optional
    latitude: Mapped[int] = mapped_column(Integer, nullable=False)
    longitude: Mapped[int] = mapped_column(Integer, nullable=False)

    @classmethod
    def create(
        cls,
        *,
        created_by,
        name: str,
        name_local: str | None,
        production_start_year: int,
        latitude: int,
        longitude: int,
    ) -> "OilGasFieldModel":
        model = cls(
            name=name,
            name_local=name_local,
            production_start_year=production_start_year,
            latitude=latitude,
            longitude=longitude,
        )
        # If your CreatedByMixin expects created_by assignment, keep this.
        # Otherwise delete these two lines.
        model.created_by_id=created_by.id,
        model.last_updated_by_id=created_by.id,
        return model
