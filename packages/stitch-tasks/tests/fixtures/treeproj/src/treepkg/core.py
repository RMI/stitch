from __future__ import annotations

__all__ = ["Widget", "build"]


def build(name: str, *, count: int = 1) -> Widget:
    return Widget(name * count)


class Widget:
    def __init__(self, name: str) -> None:
        self.name = name

    def render(self) -> str:
        return self.name

    def _hidden(self) -> None: ...


def _private() -> None: ...


UNEXPORTED = 1
