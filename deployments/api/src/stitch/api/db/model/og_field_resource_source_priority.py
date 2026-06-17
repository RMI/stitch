"""Per-resource source-priority overrides.

Lets a resource re-rank its sources, overriding the global defaults in
``og_field_source_priority``. The effective priority used during coalescing is
``COALESCE(override.priority, default.priority)`` -- absent an override row, the
default applies, so behaviour is identical to having no overrides at all.
"""

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from stitch.ogsi.model.types import OGSISrcKey

from .common import Base
from .types import PORTABLE_BIGINT


class OGFieldResourceSourcePriority(Base):
    __tablename__ = "og_field_resource_source_priority"

    resource_id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT,
        ForeignKey("og_field_resources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source: Mapped[OGSISrcKey] = mapped_column(
        String(10),
        ForeignKey("og_field_source_priority.source"),
        primary_key=True,
    )
    # Not globally unique (unlike the default table): different resources may
    # legitimately reuse the same priority value.
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
