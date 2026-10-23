"""enforce unique og_field_memberships (resource_id, source_pk)

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


def upgrade() -> None:
    with op.batch_alter_table("og_field_memberships") as batch_op:
        batch_op.create_unique_constraint(
            "uq_membership_resource_source",
            ["resource_id", "source_pk"],
        )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
