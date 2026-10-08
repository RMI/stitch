"""add og_field_memberships (resource_id, status) index

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-10-08 00:00:00.000000

`og_field_memberships` had only its primary-key index, so every read that scans a
resource's active memberships (the single-resource `source_data` join and the
coalescing universe filter, both keyed on `resource_id` + `status = ACTIVE`) fell
back to a full-table seq scan. Add a composite index on `(resource_id, status)`.

A general read win independent of the read-model work (it speeds the live
detail/source_data path too). Irreversible, per repo convention.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "e6f7a8b9c0d1"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_membership_resource_active",
        "og_field_memberships",
        ["resource_id", "status"],
    )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
