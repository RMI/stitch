"""add_og_field_resource_query_view

Revision ID: 4a65b82737c6
Revises: 6de2b873bacb
Create Date: 2026-06-17 15:16:59.870920
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4a65b82737c6"
down_revision = "6de2b873bacb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "og_field_resource_query_view",
        sa.Column(
            "resource_id",
            sa.BigInteger()
            .with_variant(sa.BIGINT(), "postgresql")
            .with_variant(sa.INTEGER(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.BigInteger()
            .with_variant(sa.BIGINT(), "postgresql")
            .with_variant(sa.INTEGER(), "sqlite"),
            nullable=False,
        ),
        sa.Column("column_name", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("value_text", sa.String(), nullable=True),
        sa.Column(
            "value_num",
            sa.Float()
            .with_variant(sa.DOUBLE_PRECISION(), "postgresql")
            .with_variant(sa.REAL(), "sqlite"),
            nullable=True,
        ),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["og_field_resources.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["oil_gas_field_sources.id"],
        ),
        sa.PrimaryKeyConstraint("resource_id", "source_id", "column_name"),
    )
    op.create_index(
        "ix_qv_colname_text",
        "og_field_resource_query_view",
        ["column_name", "source", "value_text"],
        unique=False,
    )
    op.create_index(
        "ix_qv_colname_num",
        "og_field_resource_query_view",
        ["column_name", "source", "value_num"],
        unique=False,
    )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
