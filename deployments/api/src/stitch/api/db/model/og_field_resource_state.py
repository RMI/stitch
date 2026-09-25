"""Precomputed coalesced-candidate rows per ``(resource, field)``.

Derived data, not a source of truth: every row here can be rebuilt from
memberships + source values + priorities by re-running the ranking query (see
``queries.resource_state_rows`` and ``resource_state.refresh_resource_state``).
It exists purely to keep the ``list`` / ``filter-options`` read paths off the
per-request 5-table coalescing CTE.

Each row is one candidate value for a field of a non-repointed resource, tagged
with its coalescing ``rank`` (1 = top). The full candidate list per
``(resource, field)`` is stored -- no licensing baked in. Read paths apply the
caller's licensing filter (``source IN (:licensed)``) to these rows and take the
top surviving ``rank``, reproducing today's "narrow by license, then rank".
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from .common import Base
from .oil_gas_field_source_value import ATTRIBUTE_NAMES
from .types import PORTABLE_BIGINT, PORTABLE_FLOAT, PORTABLE_JSON_NULL


class OGFieldResourceStateModel(Base):
    """One ranked candidate value for a field of a resource (see module docs)."""

    __tablename__ = "og_field_resource_state"

    resource_id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT,
        ForeignKey("og_field_resources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    colname: Mapped[str] = mapped_column(String(50), primary_key=True)
    source_pk: Mapped[int] = mapped_column(
        PORTABLE_BIGINT,
        ForeignKey("oil_gas_field_sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Coalescing rank within the (resource, colname) partition; 1 = top candidate.
    # Computed over the full candidate set (no licensing) so that removing
    # unlicensed rows at read time and taking the min surviving rank yields the
    # correct per-user winner.
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Source key, kept denormalized so the read-time licensing filter
    # (``source IN (:licensed)``) needs no join back to memberships.
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    value_text: Mapped[str | None] = mapped_column(String, nullable=True)
    value_num: Mapped[float | None] = mapped_column(PORTABLE_FLOAT, nullable=True)
    value_json: Mapped[Any | None] = mapped_column(PORTABLE_JSON_NULL, nullable=True)

    __table_args__ = (
        # colname is the same closed set as the value table.
        CheckConstraint(
            "colname IN (" + ", ".join(f"'{n}'" for n in ATTRIBUTE_NAMES) + ")",
            name="ck_resource_state_colname",
        ),
        # Read-time winner pick: filter by source, then top rank per field.
        Index("ix_resource_state_pick", "resource_id", "colname", "rank"),
        # Licensing filter / filter-options scan.
        Index("ix_resource_state_source", "source"),
    )
