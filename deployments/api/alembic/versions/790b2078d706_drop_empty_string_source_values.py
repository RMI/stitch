"""drop empty-string source values

Empty text is no longer a persistable value: NULL/absent is the single "unset"
sentinel for a source attribute. Clear any pre-existing empty-string rows, then
enforce the invariant with a CHECK so coalescing never has to treat "" as a
candidate.

Revision ID: 790b2078d706
Revises: b7e1c2f4a9d0
Create Date: 2026-07-23 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "790b2078d706"
down_revision = "b7e1c2f4a9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # An empty-string attribute meant "unset"; it is now represented by the
    # absence of a value row. Drop existing empty rows before adding the guard.
    op.execute("DELETE FROM oil_gas_field_source_values WHERE value_text = ''")
    with op.batch_alter_table("oil_gas_field_source_values") as batch_op:
        batch_op.create_check_constraint(
            "ck_source_value_text_nonempty",
            "value_text <> ''",
        )


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
