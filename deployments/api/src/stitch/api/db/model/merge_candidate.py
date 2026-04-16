from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stitch.api.entities import MergeCandidateStatus, User as UserEntity

from .common import Base
from .mixins import TimestampMixin, UserAuditMixin
from .types import PORTABLE_BIGINT


class MergeCandidateModel(TimestampMixin, UserAuditMixin, Base):
    __tablename__ = "merge_candidates"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uc_merge_candidate_fingerprint"),
    )

    id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT, primary_key=True, autoincrement=True
    )
    status: Mapped[MergeCandidateStatus] = mapped_column(
        String(20), nullable=False, default=MergeCandidateStatus.PENDING
    )
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    review_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    merged_resource_id: Mapped[int | None] = mapped_column(
        ForeignKey("og_field_resources.id"), nullable=True
    )

    items: Mapped[list["MergeCandidateItemModel"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
        order_by="MergeCandidateItemModel.position",
    )

    @classmethod
    def create(
        cls,
        *,
        created_by: UserEntity,
        fingerprint: str,
        review_notes: str | None = None,
    ) -> "MergeCandidateModel":
        return cls(
            status=MergeCandidateStatus.PENDING,
            fingerprint=fingerprint,
            review_notes=review_notes,
            created_by_id=created_by.id,
            last_updated_by_id=created_by.id,
        )


class MergeCandidateItemModel(Base):
    __tablename__ = "merge_candidate_items"
    __table_args__ = (
        UniqueConstraint(
            "merge_candidate_id",
            "resource_id",
            name="uc_merge_candidate_resource_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merge_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("merge_candidates.id"), nullable=False
    )
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("og_field_resources.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    candidate: Mapped[MergeCandidateModel] = relationship(back_populates="items")
