"""add og_field_resource_state read model

Revision ID: b1f2c3d4e5a6
Revises: 71aa7ef8150b
Create Date: 2026-09-25 00:00:00.000000

Create the precomputed current-state read model ``og_field_resource_state`` (STIT-766):
one row per ``(resource, permission_mask)`` holding the coalesced value of every
``OilGasFieldBase`` field plus a ``provenance`` map.

Schema only. The table is *derived* data and is populated by the application's
rebuild routine (``stitch.api.db.read_model.state.rebuild_all_resource_state``,
runnable via ``python -m stitch.api.db.read_model.rebuild``). Run that once after
upgrading (and after any data restore); ongoing writes keep it current in-band.
The read path falls back to live coalescing for any caller it cannot serve, so an
un-rebuilt table degrades to today's behavior rather than returning wrong data --
except for canonical (all-public) profiles, which is why the rebuild must run.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

# revision identifiers, used by Alembic.
revision = "b1f2c3d4e5a6"
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
        sa.ForeignKeyConstraint(
            ["resource_id"], ["og_field_resources.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("resource_id", "permission_mask"),
    )
    for field in _FILTER_OPTION_FIELDS:
        op.create_index(
            f"ix_og_field_resource_state_{field}",
            "og_field_resource_state",
            ["permission_mask", field],
        )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
