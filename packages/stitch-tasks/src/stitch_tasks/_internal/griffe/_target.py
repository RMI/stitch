from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

__all__ = ["resolve_target"]


def _spec_from_path(path: Path) -> tuple[str, Path]:
    resolved = path.resolve()
    if resolved.name == "__init__.py":
        resolved = resolved.parent
    parts = [resolved.stem if resolved.is_file() else resolved.name]
    parent = resolved.parent
    while (parent / "__init__.py").exists():
        parts.append(parent.name)
        parent = parent.parent
    return ".".join(reversed(parts)), parent


def resolve_target(
    target: str, search_paths: Sequence[str | Path] = ()
) -> tuple[str, list[Path] | None]:
    roots = [Path(path).resolve() for path in search_paths]
    path = Path(target)
    if path.exists():
        name, root = _spec_from_path(path)
        return name, [root, *roots]
    return target, roots or None
