"""add ccr source priority

Revision ID: e5dfcbfc32e3
Revises: f3fb36006ce6
Create Date: 2026-07-20 22:36:49.158682
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e5dfcbfc32e3"
down_revision = "f3fb36006ce6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Renumber to rmi=1, gem=2, wm=3, ccr=4, llm=5. Move llm to the (free)
    # priority 5 first so inserting ccr at 4 can't clash with the unique
    # constraint on priority.
    op.execute(
        sa.text("UPDATE og_field_source_priority SET priority = 5 WHERE source = 'llm'")
    )
    op.bulk_insert(
        sa.table(
            "og_field_source_priority",
            sa.column("source", sa.String),
            sa.column("priority", sa.Integer),
        ),
        [{"source": "ccr", "priority": 4}],
    )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
