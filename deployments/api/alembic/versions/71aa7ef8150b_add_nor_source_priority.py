"""add nor source priority

Revision ID: 71aa7ef8150b
Revises: 3a7e120d22d1
Create Date: 2026-09-23 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "71aa7ef8150b"
down_revision = "3a7e120d22d1"
branch_labels = None
depends_on = None

_REV_SOURCE_PRIORITY = ("rmi", "wm", "ccr", "bc", "alb", "nor", "gem", "llm")


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE og_field_source_priority SET priority = priority + 100")
    )
    existing = {
        row[0]
        for row in bind.execute(sa.text("SELECT source FROM og_field_source_priority"))
    }
    for priority, source in enumerate(_REV_SOURCE_PRIORITY, start=1):
        if source in existing:
            bind.execute(
                sa.text(
                    "UPDATE og_field_source_priority SET priority = :priority "
                    "WHERE source = :source"
                ).bindparams(priority=priority, source=source)
            )
        else:
            bind.execute(
                sa.text(
                    "INSERT INTO og_field_source_priority (source, priority) "
                    "VALUES (:source, :priority)"
                ).bindparams(source=source, priority=priority)
            )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
