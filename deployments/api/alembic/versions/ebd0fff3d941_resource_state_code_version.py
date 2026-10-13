"""record which code built the resource-state read model

Revision ID: ebd0fff3d941
Revises: 76427dd73cbc
Create Date: 2026-10-13 00:00:00.000000

Add ``code_version`` to ``og_field_resource_state_status``: the commit (git SHA)
of the code whose full rebuild last marked the read model ready. Readers use the
read model only when it matches their own commit, so deploying new code switches
reads to live coalescing until a rebuild by that code completes.

The existing row gets NULL, which matches no commit: reads stay live until the
next full rebuild.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "ebd0fff3d941"
down_revision = "76427dd73cbc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "og_field_resource_state_status",
        sa.Column("code_version", sa.String(), nullable=True),
    )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
