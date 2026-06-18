from __future__ import annotations

from enum import StrEnum

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from stitch.ogsi.model.types import OGSISrcKey

from stitch.api.entities import User as UserEntity

from .common import Base
from .mixins import TimestampMixin, UserAuditMixin
from .types import PORTABLE_BIGINT


class MembershipStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    INVALID = "INVALID"


class MembershipModel(TimestampMixin, UserAuditMixin, Base):
    __tablename__ = "og_field_memberships"

    id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT, primary_key=True, autoincrement=True
    )
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("og_field_resources.id"), nullable=False
    )
    source: Mapped[OGSISrcKey] = mapped_column(
        String(10),
        ForeignKey("og_field_source_priority.source"),
        nullable=False,
    )
    source_pk: Mapped[int] = mapped_column(
        ForeignKey("oil_gas_field_sources.id"), nullable=False
    )
    status: Mapped[MembershipStatus] = mapped_column(
        default=MembershipStatus.ACTIVE, nullable=False
    )

    @classmethod
    def create(
        cls,
        created_by: UserEntity,
        resource_id: int,
        source: OGSISrcKey,
        source_pk: int,
        status: MembershipStatus = MembershipStatus.ACTIVE,
    ):
        return cls(
            resource_id=resource_id,
            source=source,
            source_pk=source_pk,
            status=status,
            created_by_id=created_by.id,
            last_updated_by_id=created_by.id,
        )

    def copy(self):
        return self.__class__(
            resource_id=self.resource_id,
            source=self.source,
            source_pk=self.source_pk,
            status=self.status,
            created=self.created,
            updated=self.updated,
            created_by_id=self.created_by_id,
            last_updated_by_id=self.last_updated_by_id,
        )
