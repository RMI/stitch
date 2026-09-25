"""collapse priority tables into og_field_resource_attribute_priority

Revision ID: c2d3e4f5a6b7
Revises: b1f2c3d4e5a6
Create Date: 2026-09-25 00:00:00.000000

Replace the two-table priority split -- ``og_field_source_priority`` (global
defaults) and ``og_field_resource_source_priority`` (per-field overrides) -- with a
single per-attribute store ``og_field_resource_attribute_priority`` at the value
grain ``(resource_id, colname, source_pk)`` (STIT-766).

Backfill linearizes the old two-tier order into the single ``priority`` column:
per ``(resource, colname)``, curated rows (an override existed) take the low
contiguous positions ordered by override priority, then defaults follow ordered by
the global default priority and ``source_pk``. ``is_curated`` records which rows
were curated. Only ACTIVE memberships are backfilled (repointed resources' memberships
are INACTIVE), matching the coalescing universe.

Then drops the membership FK to ``og_field_source_priority`` and both old tables.
Irreversible, per repo convention.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

# revision identifiers, used by Alembic.
revision = "c2d3e4f5a6b7"
down_revision = "b1f2c3d4e5a6"
branch_labels = None
depends_on = None

_BIGINT = (
    sa.BigInteger()
    .with_variant(postgresql.BIGINT(), "postgresql")
    .with_variant(sqlite.INTEGER(), "sqlite")
)

_ATTRIBUTE_NAMES = (
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

_BACKFILL_SQL = """
INSERT INTO og_field_resource_attribute_priority
    (resource_id, colname, source_pk, source, priority, is_curated,
     created, updated, created_by_id, last_updated_by_id)
SELECT
    resource_id,
    colname,
    source_pk,
    source,
    ROW_NUMBER() OVER (
        PARTITION BY resource_id, colname
        ORDER BY (override_priority IS NULL), override_priority,
                 default_priority, source_pk
    ) - 1 AS priority,
    (override_priority IS NOT NULL) AS is_curated,
    now(), now(), created_by_id, last_updated_by_id
FROM (
    SELECT
        m.resource_id,
        v.colname,
        m.source_pk,
        m.source,
        o.priority AS override_priority,
        p.priority AS default_priority,
        m.created_by_id,
        m.last_updated_by_id
    FROM og_field_memberships m
    JOIN oil_gas_field_source_values v ON v.source_pk = m.source_pk
    JOIN og_field_source_priority p ON p.source = m.source
    LEFT JOIN og_field_resource_source_priority o
        ON o.resource_id = m.resource_id
       AND o.source_pk = m.source_pk
       AND o.colname = v.colname
    WHERE m.status = 'ACTIVE'
) sub
"""

_DISCOVER_MEMBERSHIP_FK_SQL = """
SELECT c.conname
FROM pg_constraint c
JOIN pg_class t ON t.oid = c.conrelid
WHERE t.relname = 'og_field_memberships'
  AND c.contype = 'f'
  AND pg_get_constraintdef(c.oid) LIKE '%og_field_source_priority%'
"""


def upgrade() -> None:
    op.create_table(
        "og_field_resource_attribute_priority",
        sa.Column("resource_id", _BIGINT, nullable=False),
        sa.Column("colname", sa.String(length=50), nullable=False),
        sa.Column("source_pk", _BIGINT, nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_curated", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint("priority >= 0", name="ck_attr_priority_nonnegative"),
        sa.CheckConstraint(
            "colname IN (" + ", ".join(f"'{n}'" for n in _ATTRIBUTE_NAMES) + ")",
            name="ck_attr_priority_colname",
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"], ["og_field_resources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_pk", "colname"],
            [
                "oil_gas_field_source_values.source_pk",
                "oil_gas_field_source_values.colname",
            ],
            name="fk_attr_priority_source_value",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["last_updated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("resource_id", "colname", "source_pk"),
        sa.UniqueConstraint(
            "resource_id", "colname", "priority", name="uq_attr_priority_position"
        ),
    )

    bind = op.get_bind()
    bind.execute(sa.text(_BACKFILL_SQL))

    # Drop the membership FK to the (about-to-be-dropped) default priority table.
    # Its name is DB-generated, so discover it on PostgreSQL.
    if bind.dialect.name == "postgresql":
        fk_name = bind.execute(sa.text(_DISCOVER_MEMBERSHIP_FK_SQL)).scalar()
        if fk_name:
            op.drop_constraint(fk_name, "og_field_memberships", type_="foreignkey")

    # Override table first (it FKs the default table), then the default table.
    op.drop_table("og_field_resource_source_priority")
    op.drop_table("og_field_source_priority")


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
