"""add ccr source priority

Adds the ``ccr`` source and sets the canonical coalescing order
``rmi=1, wm=2, ccr=3, gem=4, llm=5`` in a single step. The baseline seeds
``rmi=1, gem=2, wm=3, llm=4`` (no ccr), so this upgrades existing databases to
the final order. Values are hardcoded on purpose -- a migration is a frozen
historical snapshot, so it must not import the app's (moving) SOURCE_PRIORITY
constant; the seed-drift test keeps the two aligned.

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
    # Baseline holds rmi=1, gem=2, wm=3, llm=4 (no ccr). Move to the final order
    # rmi=1, wm=2, ccr=3, gem=4, llm=5. Offset the existing rows out of the way
    # and park the new ccr row high, then set the final order -- so no
    # intermediate state can collide with the UNIQUE constraint on priority.
    op.execute(sa.text("UPDATE og_field_source_priority SET priority = priority + 100"))
    op.bulk_insert(
        sa.table(
            "og_field_source_priority",
            sa.column("source", sa.String),
            sa.column("priority", sa.Integer),
        ),
        [{"source": "ccr", "priority": 200}],
    )
    for source, priority in (("rmi", 1), ("wm", 2), ("ccr", 3), ("gem", 4), ("llm", 5)):
        op.execute(
            sa.text(
                "UPDATE og_field_source_priority SET priority = :p WHERE source = :s"
            ).bindparams(p=priority, s=source)
        )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
