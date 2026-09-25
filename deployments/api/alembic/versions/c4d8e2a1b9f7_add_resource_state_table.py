"""precomputed resource-state (ranked coalescing candidates)

Revision ID: c4d8e2a1b9f7
Revises: 71aa7ef8150b
Create Date: 2026-09-25 00:00:00.000000

Add ``og_field_resource_state``: a precomputed table of the ranked coalescing
candidates per ``(resource, field)`` that backs the ``list`` and
``filter-options`` read paths, so they no longer rebuild the 5-table coalescing
CTE + window per request. It is derived data, maintained by the application write
paths (attach source, reprioritize, merge) and fully rebuildable at any time.

The backfill runs the same ranking builder the runtime refresh uses
(``queries.resource_state_rows``) so the stored rows cannot diverge from the live
coalescing logic.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from stitch.api.db.model import OGFieldResourceStateModel
from stitch.api.db.queries import resource_state_rows

# revision identifiers, used by Alembic.
revision = "c4d8e2a1b9f7"
down_revision = "71aa7ef8150b"
branch_labels = None
depends_on = None


_STATE_COLUMNS = [
    "resource_id",
    "colname",
    "rank",
    "source",
    "source_pk",
    "value_text",
    "value_num",
    "value_json",
]


def upgrade() -> None:
    op.create_table(
        "og_field_resource_state",
        sa.Column(
            "resource_id",
            sa.BigInteger()
            .with_variant(sa.BIGINT(), "postgresql")
            .with_variant(sa.INTEGER(), "sqlite"),
            nullable=False,
        ),
        sa.Column("colname", sa.String(length=50), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column(
            "source_pk",
            sa.BigInteger()
            .with_variant(sa.BIGINT(), "postgresql")
            .with_variant(sa.INTEGER(), "sqlite"),
            nullable=False,
        ),
        sa.Column("value_text", sa.String(), nullable=True),
        sa.Column(
            "value_num",
            sa.Float().with_variant(sa.DOUBLE_PRECISION(), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "value_json",
            sa.JSON(none_as_null=True).with_variant(
                postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), "postgresql"
            ),
            nullable=True,
        ),
        sa.CheckConstraint(
            "colname IN ('name', 'country', 'name_local', 'state_province', 'region', 'basin', 'reservoir_formation', 'location_type', 'production_conventionality', 'primary_hydrocarbon_group', 'field_status', 'latitude', 'longitude', 'discovery_year', 'production_start_year', 'fid_year', 'owners', 'operators')",
            name="ck_resource_state_colname",
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"], ["og_field_resources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_pk"], ["oil_gas_field_sources.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("resource_id", "colname", "source_pk"),
    )
    op.create_index(
        "ix_resource_state_pick",
        "og_field_resource_state",
        ["resource_id", "colname", "rank"],
        unique=False,
    )
    op.create_index(
        "ix_resource_state_source",
        "og_field_resource_state",
        ["source"],
        unique=False,
    )

    # Backfill from the same ranking builder the runtime refresh uses, so the
    # stored rows match the live coalescing logic exactly.
    bind = op.get_bind()
    bind.execute(
        sa.insert(OGFieldResourceStateModel.__table__).from_select(
            _STATE_COLUMNS, resource_state_rows()
        )
    )


def downgrade() -> None:
    raise RuntimeError("Irreversible migration: add_resource_state_table")
