from dataclasses import asdict
from typing import Any, Self

from sqlalchemy import (
    BigInteger,
    Numeric,
    String,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stitch.core.resources.domain.entities import ResourceEntity


from .base import Base, TimestampMixin

# Database-agnostic BigInteger type that works with SQLite's INTEGER autoincrement
BigIntegerType = BigInteger()
BigIntegerType = BigIntegerType.with_variant(postgresql.BIGINT(), "postgresql")
BigIntegerType = BigIntegerType.with_variant(sqlite.INTEGER(), "sqlite")


class ResourceModel(Base, TimestampMixin):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(
        BigIntegerType, primary_key=True, autoincrement=True
    )
    repointed_to: Mapped[int | None] = mapped_column(BigIntegerType, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String(3), nullable=True)
    operator: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)

    # TODO: consider using relationship for updates/creations
    memberships = relationship("MembershipModel", back_populates="resource")

    def as_entity(self) -> ResourceEntity:
        return ResourceEntity(
            id=self.id,
            repointed_to=self.repointed_to,
            name=self.name,
            country=self.country,
            operator=self.operator,
            latitude=self.latitude,
            longitude=self.longitude,
            created_by=self.created_by,
            created=self.created,
            last_updated=self.updated,
        )

    @classmethod
    def create(
        cls,
        name: str | None = None,
        country: str | None = None,
        operator: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        created_by: str | None = None,
        **_kw: Any,  # to catch the remaining attribues we don't want
    ) -> Self:
        return cls(
            name=name,
            country=country,
            operator=operator,
            latitude=latitude,
            longitude=longitude,
            created_by=created_by,
            repointed_to=None,
        )

    @classmethod
    def from_entity(cls, entity: ResourceEntity) -> Self:
        return cls.create(**asdict(entity))
