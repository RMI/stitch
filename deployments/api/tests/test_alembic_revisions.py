from __future__ import annotations

import ast
from pathlib import Path


REVISION_DIR = Path(__file__).parents[1] / "alembic" / "versions"


def _raises_runtime_error(function: ast.FunctionDef) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.Raise):
            continue

        exc = node.exc
        if isinstance(exc, ast.Call):
            exc = exc.func

        if isinstance(exc, ast.Name) and exc.id == "RuntimeError":
            return True

    return False


def test_all_alembic_revisions_have_explicit_irreversible_downgrade():
    revision_files = sorted(REVISION_DIR.glob("*.py"))

    assert revision_files, f"No Alembic revision files found in {REVISION_DIR}"

    for revision_file in revision_files:
        tree = ast.parse(revision_file.read_text(), filename=str(revision_file))

        downgrade_defs = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "downgrade"
        ]

        assert len(downgrade_defs) == 1, (
            f"{revision_file} must define exactly one downgrade() function"
        )

        assert _raises_runtime_error(downgrade_defs[0]), (
            f"{revision_file} downgrade() must explicitly raise RuntimeError"
        )
