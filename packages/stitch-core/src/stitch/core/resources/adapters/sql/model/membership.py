from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# TODO: determine a convention around imports
# fully qualified? explicit but verbose
# relative? succint and package contents can move with the package without updates
# mix of both? i.e. within a package directory, use relative, when reaching outside, use full
from stitch.core.resources.domain.entities import MembershipEntity
from .base import Base, TimestampMixin


class MembershipModel(Base, TimestampMixin):
    __tablename__ = "memberships"

    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            "source",
            "source_pk",
            name="uc_source_source_pk",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)  # "gem" | "woodmac"
    source_pk: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)

    resource = relationship("ResourceModel", back_populates="memberships")

    def as_entity(self) -> MembershipEntity:
        return MembershipEntity(
            id=self.id,
            resource_id=self.resource_id,
            source=self.source,
            source_pk=self.source_pk,
            created_by=self.created_by,
            status=self.status,
            created=self.created,
        )
