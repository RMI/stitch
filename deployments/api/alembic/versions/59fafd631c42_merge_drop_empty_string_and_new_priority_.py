"""merge drop_empty_string and add_bc_alb_source_priority heads

Reconnects two independent migration heads that both branched off the baseline:
- 790b2078d706 (drop empty-string source values) touches oil_gas_field_source_values
- 2584345b1e0d (add bc/alb source priority) touches og_field_source_priority

They operate on different tables, so this merge carries no schema change.

Revision ID: 59fafd631c42
Revises: 2584345b1e0d, 790b2078d706
Create Date: 2026-08-04 15:33:47.145055
"""

from __future__ import annotations


# revision identifiers, used by Alembic.
revision = "59fafd631c42"
down_revision = ("2584345b1e0d", "790b2078d706")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
