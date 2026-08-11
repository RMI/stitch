"""Per-resource, per-field, per-source-record priority overrides.

Lets a curator re-rank the sources for a *single field* of a resource, overriding
the global defaults in ``og_field_source_priority``. The override is keyed on the
value grain ``(resource_id, source_pk, colname)`` -- a specific source *record*
(``source_pk``) for a specific field (``colname``) -- so two records from the same
source can be ranked independently, and reordering one field never touches another.

Ranking is **tiered**: a record with an override row for a field ("curated") always
ranks above one without ("default"). See ``queries.add_ranking``:
``override_priority ASC NULLS LAST, default_priority ASC, source, source_pk``. The
``NULLS LAST`` split is why coalescing carries ``override_priority`` and
``default_priority`` as two columns rather than a single ``COALESCE``. Absent any
override row for a ``(resource, field)``, every record is in the default tier and
behaviour is identical to having no overrides at all.

Audit is lightweight (``created``/``updated``/``*_by_id`` via the mixins): it records
who last set the current ordering, not a history of prior winners.
"""

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from stitch.ogsi.model.types import OGSISrcKey

from stitch.api.entities import User as UserEntity

from .common import Base
from .mixins import TimestampMixin, UserAuditMixin
from .oil_gas_field_source_value import ATTRIBUTE_NAMES
from .types import PORTABLE_BIGINT


class OGFieldResourceSourcePriority(TimestampMixin, UserAuditMixin, Base):
    __tablename__ = "og_field_resource_source_priority"

    resource_id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT,
        ForeignKey("og_field_resources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # The specific source record ranked, not just its source class -- two records
    # from the same source (e.g. two WoodMac rows) can be ranked independently.
    source_pk: Mapped[int] = mapped_column(
        PORTABLE_BIGINT,
        ForeignKey("oil_gas_field_sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # The field this override applies to; overrides are per-field.
    colname: Mapped[str] = mapped_column(String(50), primary_key=True)
    # Kept (not part of the grain) as a ranking tiebreak and a known-source-key
    # guarantee via the FK to the default-priority table.
    source: Mapped[OGSISrcKey] = mapped_column(
        String(10),
        ForeignKey("og_field_source_priority.source"),
        nullable=False,
    )
    # Not globally unique (unlike the default table): different resources/fields may
    # legitimately reuse the same priority value. 0-based, lower = higher priority;
    # only ever compared within the curated tier of a single (resource, field).
    priority: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        # colname is the same closed, code-defined set as the value table.
        CheckConstraint(
            "colname IN (" + ", ".join(f"'{n}'" for n in ATTRIBUTE_NAMES) + ")",
            name="ck_field_priority_colname",
        ),
    )

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
    ):
        return cls(
            resource_id=resource_id,
            source=source,
            source_pk=source_pk,
            colname=colname,
            priority=priority,
            created_by_id=created_by.id,
            last_updated_by_id=created_by.id,
        )
