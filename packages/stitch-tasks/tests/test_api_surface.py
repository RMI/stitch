from __future__ import annotations

from pathlib import Path

import pytest

from stitch_tasks._internal.griffe import api_surface_markdown

FIXTURE = """__all__ = ["Widget", "build"]

ALIAS = int | str


def build(name: str, *, count: int = 1) -> str: ...


class Widget:
    def render(self) -> str: ...

    def _hidden(self) -> None: ...


def _private() -> None: ...


UNEXPORTED = 1
"""


@pytest.fixture
def surface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    package = tmp_path / "fixtpkg"
    package.mkdir()
    (package / "__init__.py").write_text(FIXTURE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return api_surface_markdown("fixtpkg")


def test_functions_are_bold_lines_with_line_number_and_return_type(
    surface: str,
) -> None:
    assert "**6: `build(name: str, *, count: int = 1) -> str`**" in surface


def test_classes_are_bold_lines(surface: str) -> None:
    assert "**9: `class Widget`**" in surface


def test_public_methods_are_prefixed_with_their_class(surface: str) -> None:
    assert "**10: `Widget.render() -> str`**" in surface


def test_private_and_unexported_names_are_omitted(surface: str) -> None:
    assert "_private" not in surface
    assert "_hidden" not in surface
    assert "UNEXPORTED" not in surface
    assert "ALIAS" not in surface
