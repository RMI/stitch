"""Guard test: source priority order must be consistent across all definitions.

The canonical order is rmi > wm > gem > llm (rmi = highest priority = 1).
This test fails if any of the four sources of truth drift from each other.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.coalesce import SRC_PRIORITY
from stitch.api.db.model.og_field_source_priority import (
    DEFAULT_PRIORITIES,
    OGFieldSourcePriority,
)

_CANONICAL_ORDER = ("rmi", "wm", "gem", "llm")

_MIGRATION_FILE = (
    Path(__file__).parents[2] / "alembic" / "versions" / "6de2b873bacb_baseline.py"
)


def _parse_migration_seed_order() -> tuple[str, ...]:
    """Extract the source order from the baseline migration's bulk_insert seed via AST."""
    tree = ast.parse(_MIGRATION_FILE.read_text(), filename=str(_MIGRATION_FILE))

    # Walk the AST to find the bulk_insert call that inserts into og_field_source_priority.
    # The call looks like: op.bulk_insert(table, [{"source": "rmi", ...}, ...])
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "bulk_insert"):
            continue
        # The second arg is the list of row dicts.
        if len(node.args) < 2:
            continue
        row_list = node.args[1]
        if not isinstance(row_list, ast.List):
            continue
        sources: list[tuple[int, str]] = []
        for elt in row_list.elts:
            if not isinstance(elt, ast.Dict):
                continue
            row: dict[str, object] = {}
            for k, v in zip(elt.keys, elt.values):
                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                    row[k.value] = v.value
            if "source" in row and "priority" in row:
                sources.append((int(row["priority"]), str(row["source"])))
        if sources:
            return tuple(src for _, src in sorted(sources))
    raise AssertionError(
        f"Could not parse og_field_source_priority seed from {_MIGRATION_FILE}"
    )


def test_src_priority_tuple_matches_canonical_order():
    """SRC_PRIORITY in coalesce.py must follow rmi > wm > gem > llm."""
    assert SRC_PRIORITY == _CANONICAL_ORDER, (
        f"coalesce.SRC_PRIORITY is {SRC_PRIORITY!r}, expected {_CANONICAL_ORDER!r}"
    )


def test_default_priorities_match_canonical_order():
    """DEFAULT_PRIORITIES in og_field_source_priority.py must follow canonical order."""
    ordered = tuple(
        row["source"] for row in sorted(DEFAULT_PRIORITIES, key=lambda r: r["priority"])
    )
    assert ordered == _CANONICAL_ORDER, (
        f"DEFAULT_PRIORITIES order is {ordered!r}, expected {_CANONICAL_ORDER!r}"
    )


def test_migration_seed_matches_canonical_order():
    """The baseline migration's bulk_insert seed is authoritative and must match."""
    migration_order = _parse_migration_seed_order()
    assert migration_order == _CANONICAL_ORDER, (
        f"Migration seed order is {migration_order!r}, expected {_CANONICAL_ORDER!r}"
    )


@pytest.mark.anyio
async def test_seeded_sqlite_table_matches_canonical_order(
    integration_session: AsyncSession,
):
    """The og_field_source_priority table seeded via after_create must match canonical order."""
    rows = (
        await integration_session.execute(
            select(OGFieldSourcePriority).order_by(OGFieldSourcePriority.priority)
        )
    ).scalars().all()
    db_order = tuple(row.source for row in rows)
    assert db_order == _CANONICAL_ORDER, (
        f"Seeded SQLite table order is {db_order!r}, expected {_CANONICAL_ORDER!r}"
    )
