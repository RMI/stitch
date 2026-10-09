"""add og_field_resource_state read model

Revision ID: 76427dd73cbc
Revises: 71aa7ef8150b
Create Date: 2026-10-09 00:00:00.000000

Create the precomputed current-state read model (STIT-766):

* ``og_field_resource_state`` -- one row per ``(resource, permission_mask)`` with
  the coalesced value of every ``OilGasFieldBase`` field plus a ``provenance`` map.
* ``og_field_resource_state_status`` -- the single readiness row, created with
  ``ready = false``.

Schema only. The table is derived data, filled by the application's full rebuild
(a required deploy step after this migration, run outside Alembic because it
reuses the app's async coalescer). Until that rebuild completes and sets
``ready = true``, reads use live coalescing, so this revision changes no answers.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

# revision identifiers, used by Alembic.
revision = "76427dd73cbc"
down_revision = "71aa7ef8150b"
branch_labels = None
depends_on = None

_BIGINT = (
    sa.BigInteger()
    .with_variant(postgresql.BIGINT(), "postgresql")
    .with_variant(sqlite.INTEGER(), "sqlite")
)
_FLOAT = (
    sa.Float()
    .with_variant(postgresql.DOUBLE_PRECISION(), "postgresql")
    .with_variant(sqlite.REAL(), "sqlite")
)
_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

_FILTER_OPTION_FIELDS = (
    "basin",
    "country",
    "field_status",
    "primary_hydrocarbon_group",
    "region",
    "state_province",
)


def upgrade() -> None:
    op.create_table(
        "og_field_resource_state",
        sa.Column("resource_id", _BIGINT, nullable=False),
        sa.Column("permission_mask", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("name_local", sa.String(), nullable=True),
        sa.Column("state_province", sa.String(), nullable=True),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("basin", sa.String(), nullable=True),
        sa.Column("reservoir_formation", sa.String(), nullable=True),
        sa.Column("location_type", sa.String(), nullable=True),
        sa.Column("production_conventionality", sa.String(), nullable=True),
        sa.Column("primary_hydrocarbon_group", sa.String(), nullable=True),
        sa.Column("field_status", sa.String(), nullable=True),
        sa.Column("latitude", _FLOAT, nullable=True),
        sa.Column("longitude", _FLOAT, nullable=True),
        sa.Column("discovery_year", sa.Integer(), nullable=True),
        sa.Column("production_start_year", sa.Integer(), nullable=True),
        sa.Column("fid_year", sa.Integer(), nullable=True),
        sa.Column("owners", _JSON, nullable=True),
        sa.Column("operators", _JSON, nullable=True),
        sa.Column("provenance", _JSON, nullable=False),
        sa.CheckConstraint(
            "permission_mask BETWEEN 0 AND 3",
            name="ck_resource_state_permission_mask",
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"], ["og_field_resources.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("resource_id", "permission_mask"),
    )
    op.create_index(
        "ix_resource_state_mask_resource",
        "og_field_resource_state",
        ["permission_mask", "resource_id"],
    )
    op.create_index(
        "ix_resource_state_mask_name",
        "og_field_resource_state",
        ["permission_mask", "name", "resource_id"],
    )
    for field in _FILTER_OPTION_FIELDS:
        op.create_index(
            f"ix_resource_state_mask_{field}",
            "og_field_resource_state",
            ["permission_mask", field],
        )

    status = op.create_table(
        "og_field_resource_state_status",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("ready", sa.Boolean(), nullable=False),
        sa.Column("rebuilt_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )
    op.bulk_insert(status, [{"key": "resource_state", "ready": False}])


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
