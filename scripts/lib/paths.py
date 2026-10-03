"""Locate the repo root and the script directories from anywhere in the tree."""

from __future__ import annotations

from functools import cache
from pathlib import Path

_ROOT_MARKER = "pyproject.toml"
_ROOT_ANCHORS = (".git", "uv.lock")


@cache
def repo_root(start: Path | None = None) -> Path:
    """The monorepo root, found by walking up from ``start`` (default: this file)."""
    origin = (start or Path(__file__)).resolve()
    candidates = origin.parents if origin.is_file() else (origin, *origin.parents)

    for directory in candidates:
        has_marker = (directory / _ROOT_MARKER).is_file()
        has_anchor = any((directory / anchor).exists() for anchor in _ROOT_ANCHORS)
        if has_marker and has_anchor:
            return directory

    raise RuntimeError(
        f"no repo root above {origin}: wanted {_ROOT_MARKER} "
        f"alongside one of {_ROOT_ANCHORS}"
    )


def scripts_dir() -> Path:
    """The repo's scripts/ directory."""
    return repo_root() / "scripts"


def data_dir() -> Path:
    """The scripts' data directory."""
    return scripts_dir() / "data"
