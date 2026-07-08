"""per-field, per-source-record priority overrides

Re-key ``og_field_resource_source_priority`` from ``(resource_id, source)`` to
``(resource_id, source_pk, colname)`` so a curator can rank individual source
records for a single field, and add lightweight who/when audit columns. The table
is empty and had no writer, so a plain drop + recreate is used (avoids a
cross-dialect PK-alter dance).

Revision ID: b7e1c2f4a9d0
Revises: f3fb36006ce6
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b7e1c2f4a9d0"
down_revision = "f3fb36006ce6"
branch_labels = None
depends_on = None

# Closed, code-defined attribute set -- mirrors oil_gas_field_source_values.colname.
_COLNAMES = (
    "name",
    "country",
    "name_local",
    "state_province",
    "region",
    "basin",
    "reservoir_formation",
    "location_type",
    "production_conventionality",
    "primary_hydrocarbon_group",
    "field_status",
    "latitude",
    "longitude",
    "discovery_year",
    "production_start_year",
    "fid_year",
    "owners",
    "operators",
)
_COLNAME_CHECK = "colname IN (" + ", ".join(f"'{n}'" for n in _COLNAMES) + ")"


def _bigint():
    return (
        sa.BigInteger()
        .with_variant(sa.BIGINT(), "postgresql")
        .with_variant(sa.INTEGER(), "sqlite")
    )


def upgrade() -> None:
    op.drop_table("og_field_resource_source_priority")
    op.create_table(
        "og_field_resource_source_priority",
        sa.Column("resource_id", _bigint(), nullable=False),
        sa.Column("source_pk", _bigint(), nullable=False),
        sa.Column("colname", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column(
            "created",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("last_updated_by_id", sa.Integer(), nullable=False),
        sa.CheckConstraint(_COLNAME_CHECK, name="ck_resource_source_priority_colname"),
        sa.ForeignKeyConstraint(
            ["resource_id"], ["og_field_resources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_pk"], ["oil_gas_field_sources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source"], ["og_field_source_priority.source"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["last_updated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("resource_id", "source_pk", "colname"),
    )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
