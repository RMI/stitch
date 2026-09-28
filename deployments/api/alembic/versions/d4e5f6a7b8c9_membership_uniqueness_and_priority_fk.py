"""enforce membership uniqueness and priority->membership FK

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-09-28 00:00:00.000000

Close the integrity gap on og_field_resource_attribute_priority: its rows proved a
source has a value for a field, but not that the source is actually attached to the
resource. Enforce it structurally (STIT-766, Copilot review):

1. Dedup og_field_memberships to one row per (resource_id, source_pk), keeping the
   ACTIVE row when present, else the lowest id. (The write paths now dedup on
   attach and merge; this cleans any pre-existing duplicates.)
2. Add UNIQUE (resource_id, source_pk) on og_field_memberships.
3. Add composite FK og_field_resource_attribute_priority (resource_id, source_pk)
   -> og_field_memberships (resource_id, source_pk), so a priority row can only
   reference a source that is a real member of its resource.

Irreversible, per repo convention.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None

# Keep exactly one membership per (resource_id, source_pk): a row is removed when a
# strictly-preferred sibling exists (ACTIVE beats non-ACTIVE; within the same
# active-ness, the lowest id wins).
_DEDUP_MEMBERSHIPS_SQL = """
DELETE FROM og_field_memberships m
WHERE EXISTS (
    SELECT 1
    FROM og_field_memberships k
    WHERE k.resource_id = m.resource_id
      AND k.source_pk = m.source_pk
      AND k.id <> m.id
      AND (
          (k.status = 'ACTIVE' AND m.status <> 'ACTIVE')
          OR ((k.status = 'ACTIVE') = (m.status = 'ACTIVE') AND k.id < m.id)
      )
)
"""


def upgrade() -> None:
    op.execute(sa.text(_DEDUP_MEMBERSHIPS_SQL))
    op.create_unique_constraint(
        "uq_membership_resource_source",
        "og_field_memberships",
        ["resource_id", "source_pk"],
    )
    op.create_foreign_key(
        "fk_attr_priority_membership",
        "og_field_resource_attribute_priority",
        "og_field_memberships",
        ["resource_id", "source_pk"],
        ["resource_id", "source_pk"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
