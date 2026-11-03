from __future__ import annotations

from collections.abc import Iterator, Sequence
from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

from griffe import Alias, Attribute, Class, Function, Kind, load

from ._target import resolve_target

if TYPE_CHECKING:
    from griffe import Object

__all__ = [
    "DEFAULT_EXCLUDES",
    "TOP_LEVEL_KINDS",
    "api_surface_markdown",
    "directory_surface_markdown",
    "public_members",
    "resolve_target",
    "signature_of",
]

TOP_LEVEL_KINDS = (Kind.FUNCTION, Kind.CLASS, Kind.ATTRIBUTE)

DEFAULT_EXCLUDES = (
    "__pycache__",
    ".venv",
    "venv",
    "tests",
    "test",
    "conftest.py",
    "setup.py",
    "build",
    "dist",
    "*.egg-info",
    "node_modules",
    "alembic",
    "migrations",
)


def public_members(
    parent: Object | Alias, kinds: tuple[Kind, ...]
) -> Iterator[tuple[int, Object | Alias]]:
    found: list[tuple[int, Object | Alias]] = []
    for member in parent.members.values():
        if isinstance(member, Alias) or not member.is_public:
            continue
        if member.kind not in kinds or member.lineno is None:
            continue
        found.append((member.lineno, member))
    yield from sorted(found, key=lambda pair: pair[0])


def signature_of(obj: Object | Alias) -> str:
    target = obj.final_target if isinstance(obj, Alias) else obj
    if isinstance(target, Class):
        bases = ", ".join(str(base) for base in target.bases)
        return f"class {target.name}({bases})" if bases else f"class {target.name}"
    if isinstance(target, Function):
        return target.signature(return_type=True)
    if isinstance(target, Attribute):
        if target.annotation is not None:
            return f"{target.name}: {target.annotation}"
        if target.value is not None:
            return f"{target.name} = {target.value}"
    return target.name


def _entry(lineno: int, obj: Object | Alias, prefix: str = "") -> str:
    return f"- **{lineno}: `{prefix}{signature_of(obj)}`**"


def _member_lines(module: Object | Alias) -> list[str]:
    lines: list[str] = []
    for lineno, member in public_members(module, TOP_LEVEL_KINDS):
        lines.extend([_entry(lineno, member)])
        if member.kind is Kind.CLASS:
            for method_lineno, method in public_members(member, (Kind.FUNCTION,)):
                lines.extend([_entry(method_lineno, method, f"{member.name}.")])
    return lines


def _api_surface_lines(module: Object | Alias) -> list[str]:
    return [str(module), *_member_lines(module)]


def api_surface_markdown(module_name: str) -> str:
    _, *memberlines = _api_surface_lines(load(module_name))
    return "\n".join([f"# `{module_name}`", "", *memberlines])


def _is_excluded(path: Path, directory: Path, patterns: Sequence[str]) -> bool:
    return any(
        part.startswith(".") or any(fnmatch(part, pattern) for pattern in patterns)
        for part in path.relative_to(directory).parts
    )


def _module_paths(directory: Path, patterns: Sequence[str]) -> Iterator[Path]:
    for path in sorted(directory.rglob("*.py")):
        if not _is_excluded(path, directory, patterns):
            yield path


def _package_root(path: Path, fallback: Path) -> Path:
    for parent in path.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return fallback


def directory_surface_markdown(
    directory: str,
    exclude: Sequence[str] = (),
    title: str = "",
    heading_base: Path | None = None,
) -> str:
    root = Path(directory).resolve()
    base = heading_base.resolve() if heading_base else None
    patterns = (*DEFAULT_EXCLUDES, *exclude)
    lines = [f"# `{title or root.name}`", ""]
    for path in _module_paths(root, patterns):
        name, search_paths = resolve_target(str(path))
        modname, *members = _api_surface_lines(load(name, search_paths=search_paths))
        if not members:
            continue
        heading = path.relative_to(base or _package_root(path, root)).as_posix()
        lines.extend([f"## `{heading}`", "", *members, ""])
    return "\n".join(lines)
