from __future__ import annotations

from pathlib import Path

import pytest

from stitch_tasks._internal.workspace import resolve_package, workspace_packages


def make_project(root: Path, name: str, build_backend: str = "") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\n{build_backend}', encoding="utf-8"
    )
    return root


def test_default_module_name_is_the_normalised_project_name(tmp_path: Path) -> None:
    root = make_project(tmp_path / "proj", "my-pkg")
    assert resolve_package(str(root)) == ("my-pkg", root / "src" / "my_pkg")


def test_dotted_module_name_becomes_a_nested_directory(tmp_path: Path) -> None:
    root = make_project(
        tmp_path / "api",
        "stitch-api",
        '[tool.uv.build-backend]\nmodule-name = "stitch.api"\n',
    )
    assert resolve_package(str(root)) == ("stitch-api", root / "src" / "stitch" / "api")


def test_module_root_is_honoured(tmp_path: Path) -> None:
    root = make_project(
        tmp_path / "flat",
        "flat-pkg",
        '[tool.uv.build-backend]\nmodule-root = ""\n',
    )
    assert resolve_package(str(root)) == ("flat-pkg", root / "flat_pkg")


def test_a_path_inside_a_project_resolves_to_the_project(tmp_path: Path) -> None:
    root = make_project(tmp_path / "proj", "my-pkg")
    nested = root / "src" / "my_pkg" / "sub"
    nested.mkdir(parents=True)
    assert resolve_package(str(nested)) == ("my-pkg", root / "src" / "my_pkg")


def test_several_modules_are_rejected(tmp_path: Path) -> None:
    root = make_project(
        tmp_path / "multi",
        "multi-pkg",
        '[tool.uv.build-backend]\nmodule-name = ["foo", "bar"]\n',
    )
    with pytest.raises(ValueError, match="several modules"):
        resolve_package(str(root))


def test_an_unknown_target_is_rejected() -> None:
    with pytest.raises(ValueError, match="not a path inside a project"):
        resolve_package("no-such-package-anywhere")


def test_an_installed_package_resolves_by_name() -> None:
    name, directory = resolve_package("stitch-tasks")
    assert name == "stitch-tasks"
    assert directory == Path(__file__).resolve().parents[1] / "src" / "stitch_tasks"


def make_member(root: Path, name: str, with_module: bool = True) -> Path:
    make_project(root, name)
    if with_module:
        (root / "src" / name.replace("-", "_")).mkdir(parents=True)
    return root


def make_workspace(root: Path, members: str, exclude: str = "") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        f"[tool.uv.workspace]\nmembers = {members}\n{exclude}", encoding="utf-8"
    )
    return root


def test_workspace_packages_finds_every_member(tmp_path: Path) -> None:
    root = make_workspace(tmp_path / "ws", '["packages/*"]')
    make_member(root / "packages" / "beta", "pkg-beta")
    make_member(root / "packages" / "alpha", "pkg-alpha")

    assert workspace_packages(root) == [
        ("pkg-alpha", root / "packages" / "alpha" / "src" / "pkg_alpha"),
        ("pkg-beta", root / "packages" / "beta" / "src" / "pkg_beta"),
    ]


def test_workspace_packages_skips_members_without_a_module_directory(
    tmp_path: Path,
) -> None:
    root = make_workspace(tmp_path / "ws", '["packages/*"]')
    make_member(root / "packages" / "real", "pkg-real")
    make_member(root / "packages" / "bare", "pkg-bare", with_module=False)

    assert [name for name, _ in workspace_packages(root)] == ["pkg-real"]


def test_workspace_packages_honours_exclude(tmp_path: Path) -> None:
    root = make_workspace(
        tmp_path / "ws", '["packages/*"]', 'exclude = ["packages/skipme"]\n'
    )
    make_member(root / "packages" / "keep", "pkg-keep")
    make_member(root / "packages" / "skipme", "pkg-skip")

    assert [name for name, _ in workspace_packages(root)] == ["pkg-keep"]


def test_workspace_packages_searches_upwards(tmp_path: Path) -> None:
    root = make_workspace(tmp_path / "ws", '["packages/*"]')
    member = make_member(root / "packages" / "alpha", "pkg-alpha")

    assert workspace_packages(member / "src" / "pkg_alpha") == workspace_packages(root)


def test_workspace_packages_without_a_workspace_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No uv workspace"):
        workspace_packages(tmp_path)
