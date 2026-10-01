"""Locate the repo root and the script directories from anywhere in the tree."""

from __future__ import annotations

from functools import cache
from pathlib import Path

# Every workspace member carries a pyproject.toml, so that file alone does not
# identify the root. Pair it with a marker only the root has.
_ROOT_MARKER = "pyproject.toml"
_ROOT_ANCHORS = (".git", "uv.lock")


@cache
def repo_root(start: Path | None = None) -> Path:
    """The monorepo root, found by walking up from ``start`` (default: this file).

    Raises rather than falling back to a guess: a wrong root silently resolves
    every other path in this package to the wrong tree.
    """
    origin = (start or Path(__file__)).resolve()
    # ``parents`` excludes the path itself, which is right for a file and wrong
    # for a directory that is already the root.
    candidates = origin.parents if origin.is_file() else (origin, *origin.parents)

    for directory in candidates:
        has_marker = (directory / _ROOT_MARKER).is_file()
        # ``.git`` is a file, not a directory, inside a linked worktree.
        has_anchor = any((directory / anchor).exists() for anchor in _ROOT_ANCHORS)
        if has_marker and has_anchor:
            return directory

    raise RuntimeError(
        f"no repo root above {origin}: wanted {_ROOT_MARKER} "
        f"alongside one of {_ROOT_ANCHORS}"
    )


def scripts_dir() -> Path:
    return repo_root() / "scripts"


def data_dir() -> Path:
    return scripts_dir() / "data"
