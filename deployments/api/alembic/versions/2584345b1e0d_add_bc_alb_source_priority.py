"""add bc alb source priority

Revision ID: 2584345b1e0d
Revises: 2445c5141f3d
Create Date: 2026-07-23 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "2584345b1e0d"
down_revision = "2445c5141f3d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Predecessor (reorder_source_priority) leaves rmi=1, wm=2, ccr=3, gem=4,
    # llm=5. Reorder to rmi=1, wm=2, ccr=3, bc=4, alb=5, gem=6, llm=7 and insert
    # the bc/alb rows. Each UPDATE moves a source into a slot that is free at that
    # point, so the unique constraint on priority is never violated:
    #   gem 4 -> 6 (frees 4), llm 5 -> 7 (frees 5), wm -> 2 and ccr -> 3 are
    #   no-ops here, then insert bc=4, alb=5 into the now-free slots.
    for source, priority in (
        ("gem", 6),
        ("llm", 7),
        ("wm", 2),
        ("ccr", 3),
    ):
        op.execute(
            sa.text(
                "UPDATE og_field_source_priority SET priority = :priority "
                "WHERE source = :source"
            ).bindparams(priority=priority, source=source)
        )
    op.bulk_insert(
        sa.table(
            "og_field_source_priority",
            sa.column("source", sa.String),
            sa.column("priority", sa.Integer),
        ),
        [{"source": "bc", "priority": 4}, {"source": "alb", "priority": 5}],
    )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
