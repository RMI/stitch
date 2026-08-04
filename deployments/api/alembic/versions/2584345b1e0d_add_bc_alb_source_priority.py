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

# Frozen snapshot of ``stitch.ogsi.model.SOURCE_PRIORITY`` as of this revision.
# Migrations are historical records, so this is intentionally hardcoded rather
# than imported: importing the live constant would silently rewrite what this
# already-applied revision means whenever the canonical order changes. If
# SOURCE_PRIORITY changes, add a NEW revision -- do not edit this tuple.
_REV_SOURCE_PRIORITY = ("rmi", "wm", "ccr", "bc", "alb", "gem", "llm")


def upgrade() -> None:
    # Bring og_field_source_priority to exactly _REV_SOURCE_PRIORITY (priority =
    # 1-based index). Two other tables FK to this table's ``source`` column
    # (og_field_resource_source_priority, og_field_memberships), so we cannot
    # drop or delete rows -- we upsert in place: UPDATE the sources that already
    # exist and INSERT the new ones (bc, alb). First offset every existing row
    # past the target range so the per-source UPDATEs below can't transiently
    # collide with the UNIQUE constraint on ``priority``.
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
