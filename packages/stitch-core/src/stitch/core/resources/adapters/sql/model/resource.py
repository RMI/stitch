from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Mapped, mapped_column, relationship


from .base import Base

# Database-agnostic BigInteger type that works with SQLite's INTEGER autoincrement
BigIntegerType = BigInteger()
BigIntegerType = BigIntegerType.with_variant(postgresql.BIGINT(), "postgresql")
BigIntegerType = BigIntegerType.with_variant(sqlite.INTEGER(), "sqlite")


class ResourceModel(Base):
    __tablename__ = "resources"
    __table_args__ = (
        UniqueConstraint("dataset", "source_pk", name="uq_dataset_source_pk"),
    )

    id: Mapped[int] = mapped_column(
        BigIntegerType, primary_key=True, autoincrement=True
    )
    repointed_id: Mapped[int | None] = mapped_column(BigIntegerType, nullable=True)

    # "gem" | "woodmac", nullable for aggregate resources
    dataset: Mapped[str] = mapped_column(String, nullable=True)

    # nullable for aggregate resources
    source_pk: Mapped[str] = mapped_column(String, nullable=True)

    name: Mapped[str | None] = mapped_column(String, nullable=True)
    country_iso3: Mapped[str | None] = mapped_column(String(3), nullable=True)
    operator: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)

    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    memberships = relationship("MembershipModel", back_populates="resource")
