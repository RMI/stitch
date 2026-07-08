"""Per-(resource, source-record, field) source-priority overrides.

Lets a resource re-rank its individual source *records* for a single field,
overriding the global defaults in ``og_field_source_priority``. Each row pins one
``(resource_id, source_pk, colname)`` to an explicit ``priority``.

During coalescing an *overridden* record always outranks a non-overridden one for
that field (SQL: ``override_priority ASC NULLS LAST``; Python: an explicit tier
bit), so a record that gains no override row -- e.g. a source added *after* a
curator reordered the field -- sorts last, below every pinned record, ordered by
its global default. Absent any override row for a field, behaviour is identical to
having no overrides at all.

Audit is lightweight (who/when for the *current* ordering) via the shared mixins.
Because a save replaces the whole ``(resource, field)`` snapshot, prior orderings
are not retained -- reconstructing a previous winner would need an append-only
history table, deferred for now.
"""

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from stitch.api.entities import User as UserEntity
from stitch.ogsi.model.types import OGSISrcKey

from .common import Base
from .mixins import TimestampMixin, UserAuditMixin
from .oil_gas_field_source_value import ATTRIBUTE_NAMES
from .types import PORTABLE_BIGINT

_COLNAME_CHECK = "colname IN (" + ", ".join(f"'{n}'" for n in ATTRIBUTE_NAMES) + ")"


class OGFieldResourceSourcePriority(TimestampMixin, UserAuditMixin, Base):
    __tablename__ = "og_field_resource_source_priority"

    __table_args__ = (
        # colname is the same closed, code-defined set as the value table.
        CheckConstraint(_COLNAME_CHECK, name="ck_resource_source_priority_colname"),
    )

    resource_id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT,
        ForeignKey("og_field_resources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # The override keys on a specific source *record* (not the source key), so a
    # resource with multiple records from the same source (e.g. two WoodMac
    # records) can be ranked individually.
    source_pk: Mapped[int] = mapped_column(
        PORTABLE_BIGINT,
        ForeignKey("oil_gas_field_sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    colname: Mapped[str] = mapped_column(String(50), primary_key=True)
    # Denormalized source key: kept as the ranking tiebreak and to preserve the
    # "source is a known priority key" guarantee via the FK below.
    source: Mapped[OGSISrcKey] = mapped_column(
        String(10),
        ForeignKey("og_field_source_priority.source"),
        nullable=False,
    )
    # Not globally unique (unlike the default table): different resources/fields
    # may legitimately reuse the same priority value.
    priority: Mapped[int] = mapped_column(Integer, nullable=False)

    @classmethod
    def create(
        cls,
        *,
        created_by: UserEntity,
        resource_id: int,
        source: OGSISrcKey,
        source_pk: int,
        colname: str,
        priority: int,
    ) -> "OGFieldResourceSourcePriority":
        return cls(
            resource_id=resource_id,
            source=source,
            source_pk=source_pk,
            colname=colname,
            priority=priority,
            created_by_id=created_by.id,
            last_updated_by_id=created_by.id,
        )
