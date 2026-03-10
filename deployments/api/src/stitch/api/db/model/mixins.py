from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, func

from sqlalchemy.orm import Mapped, declarative_mixin, mapped_column


@declarative_mixin
class TimestampMixin:
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


@declarative_mixin
class UserAuditMixin:
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    last_updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
