"""reorder source priority

Revision ID: 2445c5141f3d
Revises: e5dfcbfc32e3
Create Date: 2026-07-23 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "2445c5141f3d"
down_revision = "e5dfcbfc32e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Renumber to rmi=1, wm=2, ccr=3, gem=4, llm=5 (gem drops from 2 to 4).
    # Offset every row out of the way first so the intermediate states can't
    # collide with the UNIQUE constraint on priority.
    op.execute(sa.text("UPDATE og_field_source_priority SET priority = priority + 100"))
    for source, priority in (("rmi", 1), ("wm", 2), ("ccr", 3), ("gem", 4), ("llm", 5)):
        op.execute(
            sa.text(
                "UPDATE og_field_source_priority SET priority = :p WHERE source = :s"
            ).bindparams(p=priority, s=source)
        )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
