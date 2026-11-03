from __future__ import annotations

import json
import tomllib
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from urllib.parse import unquote, urlparse

__all__ = ["resolve_package", "workspace_packages"]


def _load(root: Path) -> dict:
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))


def _project_root(path: Path) -> Path | None:
    for candidate in [path, *path.parents]:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return None


def _installed_root(name: str) -> Path | None:
    try:
        direct_url = distribution(name).read_text("direct_url.json")
    except PackageNotFoundError:
        return None
    if not direct_url:
        return None
    root = Path(unquote(urlparse(json.loads(direct_url)["url"]).path))
    return root if (root / "pyproject.toml").is_file() else None


def _module_dir(root: Path, name: str) -> Path:
    settings = _load(root).get("tool", {}).get("uv", {}).get("build-backend", {})
    module_name = settings.get("module-name", name.replace("-", "_").replace(".", "_"))
    if not isinstance(module_name, str):
        raise ValueError(
            f"Package {name!r} declares several modules ({module_name}); "
            "point the task at one module directory instead"
        )
    return root / settings.get("module-root", "src") / Path(*module_name.split("."))


def resolve_package(target: str) -> tuple[str, Path]:
    """
    Resolve a package name or path to its distribution name and module directory.

    :param target: An installed package name, or a path within a project
    :return: The distribution name and the directory holding its modules
    """
    path = Path(target)
    root = _project_root(path.resolve()) if path.exists() else _installed_root(target)
    if root is None:
        raise ValueError(
            f"{target!r} is not a path inside a project, nor an installed "
            "package resolvable to one; run 'uv sync --all-packages' first"
        )
    name = _load(root).get("project", {}).get("name", root.name)
    return name, _module_dir(root, name)


def workspace_packages(start: Path | None = None) -> list[tuple[str, Path]]:
    """
    Find every uv workspace member that has a module directory on disk.

    :param start: Directory to search upwards from, defaults to the cwd
    :return: The name and module directory of each member, ordered by name
    """
    base = (start or Path.cwd()).resolve()
    for candidate in [base, *base.parents]:
        if not (candidate / "pyproject.toml").is_file():
            continue
        workspace = _load(candidate).get("tool", {}).get("uv", {}).get("workspace", {})
        if not workspace.get("members"):
            continue
        excluded = {
            path
            for pattern in workspace.get("exclude", [])
            for path in candidate.glob(pattern)
        }
        members = [
            resolve_package(str(path))
            for pattern in workspace["members"]
            for path in sorted(candidate.glob(pattern))
            if path not in excluded and (path / "pyproject.toml").is_file()
        ]
        return sorted({member for member in members if member[1].is_dir()})
    raise ValueError(f"No uv workspace found at or above {base}")
