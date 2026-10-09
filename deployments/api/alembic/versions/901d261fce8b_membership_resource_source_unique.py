"""enforce unique og_field_memberships (resource_id, source_pk)

A source record could be attached to the same resource more than once. Collapse
any pre-existing duplicates to one row per (resource_id, source_pk), then enforce
the invariant with a UNIQUE constraint. Uniqueness is per (resource, source): a
source record may still belong to several different resources.

Dedup keeps the ACTIVE row when one exists, otherwise the lowest id. Nothing
references og_field_memberships.id, and per-resource priority overrides are keyed
by (resource_id, source_pk), so they are unaffected by which row is kept.

Revision ID: 901d261fce8b
Revises: 71aa7ef8150b
Create Date: 2026-10-09 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "901d261fce8b"
down_revision = "71aa7ef8150b"
branch_labels = None
depends_on = None

_DEDUP_MEMBERSHIPS_SQL = """
DELETE FROM og_field_memberships
WHERE id IN (
    SELECT id
    FROM (
        SELECT
            id,
            ROW_NUMBER() OVER (
                PARTITION BY resource_id, source_pk
                ORDER BY CASE WHEN status = 'ACTIVE' THEN 0 ELSE 1 END, id
            ) AS rn
        FROM og_field_memberships
    ) ranked
    WHERE ranked.rn > 1
)
"""


def upgrade() -> None:
    op.execute(_DEDUP_MEMBERSHIPS_SQL)
    op.create_unique_constraint(
        "uq_membership_resource_source",
        "og_field_memberships",
        ["resource_id", "source_pk"],
    )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
