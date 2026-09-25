"""Single per-attribute source priority store (STIT-766).

Replaces the two-table split of global defaults (``og_field_source_priority``) and
per-field overrides (``og_field_resource_source_priority``) with one table at the
value grain ``(resource_id, colname, source_pk)`` -- one row per source record that
carries a value for a field of a resource.

Ranking collapses to a single column: ``priority`` (0-based, lower wins), unique
within each ``(resource, colname)``. The old two-tier order is *linearized* into
it -- curated rows (``is_curated``) occupy the low, contiguous positions and always
outrank the default rows that follow, which are ordered by the global
``SOURCE_PRIORITY`` rank (see ``db.source_priority``) then ``source_pk``. So the
coalescing query is just ``ORDER BY priority`` with no NULLS-LAST tiering.

``is_curated`` marks rows a user explicitly re-ranked; it powers the ``is_override``
flag the API exposes and lets the default-seeding path (``db.priorities``) rebuild
default rows without disturbing curation. Rows are maintained inside the writing
transaction and are fully rebuildable from memberships + values.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from stitch.ogsi.model.types import OGSISrcKey

from stitch.api.entities import User as UserEntity

from .common import Base
from .mixins import TimestampMixin, UserAuditMixin
from .oil_gas_field_source_value import ATTRIBUTE_NAMES
from .types import PORTABLE_BIGINT


class OGFieldResourceAttributePriority(TimestampMixin, UserAuditMixin, Base):
    __tablename__ = "og_field_resource_attribute_priority"

    resource_id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT,
        ForeignKey("og_field_resources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    colname: Mapped[str] = mapped_column(String(50), primary_key=True)
    # The specific source record ranked (two records of one source key rank
    # independently), part of the grain.
    source_pk: Mapped[int] = mapped_column(
        PORTABLE_BIGINT,
        primary_key=True,
    )
    # Kept as a ranking input (global default order) and a known-source-key value.
    source: Mapped[OGSISrcKey] = mapped_column(String(10), nullable=False)
    # 0-based, lower wins; unique within a (resource, colname). Curated rows take
    # the low contiguous positions, defaults follow.
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    # True when a user explicitly ranked this row (surfaced as ``is_override``).
    is_curated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint(
            "resource_id", "colname", "priority", name="uq_attr_priority_position"
        ),
        CheckConstraint("priority >= 0", name="ck_attr_priority_nonnegative"),
        CheckConstraint(
            "colname IN (" + ", ".join(f"'{n}'" for n in ATTRIBUTE_NAMES) + ")",
            name="ck_attr_priority_colname",
        ),
        # The row must reference a populated source value for the field.
        ForeignKeyConstraint(
            ["source_pk", "colname"],
            [
                "oil_gas_field_source_values.source_pk",
                "oil_gas_field_source_values.colname",
            ],
            name="fk_attr_priority_source_value",
            ondelete="CASCADE",
        ),
    )

    @classmethod
    def create(
        cls,
        *,
        created_by: UserEntity,
        resource_id: int,
        colname: str,
        source: OGSISrcKey,
        source_pk: int,
        priority: int,
        is_curated: bool,
    ):
        return cls(
            resource_id=resource_id,
            colname=colname,
            source=source,
            source_pk=source_pk,
            priority=priority,
            is_curated=is_curated,
            created_by_id=created_by.id,
            last_updated_by_id=created_by.id,
        )
