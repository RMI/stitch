"""record which code computed each resource-state row

Revision ID: 2a1562956888
Revises: ebd0fff3d941
Create Date: 2026-10-14 00:00:00.000000

Add ``code_version`` to ``og_field_resource_state``: the commit (git SHA) of the
code that computed each row. A full rebuild recomputes rows computed by other
code (for example an older API revision still writing during a deploy) before
marking the table ready, so the table is never served under one commit with
rows computed by another.

Existing rows get NULL, which matches no commit: the next rebuild recomputes
them.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "2a1562956888"
down_revision = "ebd0fff3d941"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "og_field_resource_state",
        sa.Column("code_version", sa.String(), nullable=True),
    )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
