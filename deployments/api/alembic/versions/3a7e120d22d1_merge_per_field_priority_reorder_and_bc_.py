"""merge per-field priority reorder and bc/alb source priority heads

Joins the two divergent Alembic heads created when ``main`` (which added the
``bc``/``alb`` default source priorities in ``2584345b1e0d``) was merged into the
per-field source-reorder branch (``a3f5c2e9b1d4``). The two lineages touch disjoint
tables -- ``og_field_source_priority`` (data) vs ``og_field_resource_source_priority``
(schema) -- so this merge carries no DDL of its own.

Revision ID: 3a7e120d22d1
Revises: 59fafd631c42, 20f3722fdba4
Create Date: 2026-08-05 18:43:21.015679
"""

from __future__ import annotations


# revision identifiers, used by Alembic.
revision = "3a7e120d22d1"
down_revision = ("59fafd631c42", "20f3722fdba4")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    raise RuntimeError(f"Irreversible migration: {revision}")
