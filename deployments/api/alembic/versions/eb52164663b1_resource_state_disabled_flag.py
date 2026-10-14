"""let operators switch the resource-state read model off

Revision ID: eb52164663b1
Revises: 2a1562956888
Create Date: 2026-10-14 00:00:00.000000

Add ``disabled`` to ``og_field_resource_state_status``: an operator's switch to
keep the API on live reads. Rebuilds keep the rows current but never clear it,
so a deploy's automatic rebuild can't turn the read model back on. Existing rows
get ``false`` (unchanged behaviour).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "eb52164663b1"
down_revision = "2a1562956888"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "og_field_resource_state_status",
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
