from datetime import datetime
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class MembershipModel(Base):
    __tablename__ = "memberships"

    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            "dataset",
            "source_pk",
            name="uq_dataset_source_pk",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), nullable=False)
    dataset: Mapped[str] = mapped_column(String, nullable=False)  # "gem" | "woodmac"
    source_pk: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    resource = relationship("ResourceModel", back_populates="memberships")
