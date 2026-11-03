from __future__ import annotations

from pathlib import Path

import pytest

from stitch_tasks._internal.griffe import directory_surface_markdown

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def surface() -> str:
    return directory_surface_markdown(str(FIXTURES / "treeproj"))


def test_matches_the_expected_markdown(surface: str) -> None:
    assert surface == (FIXTURES / "treeproj.md").read_text(encoding="utf-8")


def test_cache_directories_are_skipped(tmp_path: Path) -> None:
    cached = tmp_path / "__pycache__"
    cached.mkdir()
    (cached / "stale.py").write_text("def ghost() -> None: ...\n", encoding="utf-8")
    assert "ghost" not in directory_surface_markdown(str(tmp_path))


@pytest.mark.parametrize("excluded", ["tests", ".venv", "alembic", "thing.egg-info"])
def test_default_excludes_are_skipped(tmp_path: Path, excluded: str) -> None:
    (tmp_path / excluded).mkdir()
    (tmp_path / excluded / "mod.py").write_text(
        "def ghost() -> None: ...\n", encoding="utf-8"
    )
    assert "ghost" not in directory_surface_markdown(str(tmp_path))


def test_extra_excludes_add_to_the_defaults(tmp_path: Path) -> None:
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "mod.py").write_text(
        "def ghost() -> None: ...\n", encoding="utf-8"
    )
    (tmp_path / "kept.py").write_text("def keeper() -> None: ...\n", encoding="utf-8")

    assert "ghost" in directory_surface_markdown(str(tmp_path))

    surface = directory_surface_markdown(str(tmp_path), ["generated"])
    assert "ghost" not in surface
    assert "keeper" in surface


def test_modules_without_public_members_are_omitted(surface: str) -> None:
    assert "src/treepkg/sub/__init__.py" not in surface
    assert "src/treepkg/sub/deep.py" in surface


def test_reexports_are_omitted_from_the_module_that_imports_them(
    surface: str,
) -> None:
    assert "## `src/treepkg/__init__.py`" in surface
    assert "VERSION" in surface
    assert surface.count("class Widget") == 1


def test_modules_that_only_reexport_are_omitted(surface: str) -> None:
    assert "src/treepkg/facade.py" not in surface
    assert "make" not in surface


def test_heading_base_makes_headings_relative_to_it() -> None:
    package = FIXTURES / "treeproj" / "src" / "treepkg"
    surface = directory_surface_markdown(
        str(package), title="treepkg", heading_base=package
    )
    assert surface.startswith("# `treepkg`\n")
    assert "## `core.py`" in surface
    assert "## `sub/deep.py`" in surface
    assert "src/treepkg" not in surface
