from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from poethepoet_tasks import TaskCollection

from ._internal.griffe import (
    DEFAULT_EXCLUDES,
    api_surface_markdown,
    directory_surface_markdown,
)
from ._internal.npm import FRONTEND_PACKAGE, frontend_api_surface
from ._internal.openai import responses_joke
from ._internal.workspace import resolve_package, workspace_packages

tasks = TaskCollection()


def _surface_args(target: str, target_help: str, required: bool = True) -> list[dict]:
    positional = {
        "name": target,
        "positional": True,
        "required": required,
        "help": target_help,
    }
    if not required:
        positional["default"] = ""
    return [
        positional,
        {
            "name": "output",
            "options": ["-o", "--output"],
            "default": "",
            "help": f"Destination path, defaults to docs/<name>-{target}.md",
        },
    ]


def _path_args() -> list[dict]:
    return [
        {
            "name": "exclude",
            "options": ["-x", "--exclude"],
            "multiple": True,
            "help": (
                "File or directory names to skip, in addition to dotted names "
                f"and {', '.join(DEFAULT_EXCLUDES)}"
            ),
        },
    ]


def _emit(markdown: str, output: str, stem: str, kind: str) -> None:
    path = Path(output) if output else Path("docs") / f"{stem}-{kind}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    print(path)


@tasks.script(
    task_name="api:module",
    help="Write a module's public top-level API surface as markdown",
    task_args=False,
    options={"args": _surface_args("module", "Importable module path")},
    tags=["docs"],
)
def api_module(module: str, *, output: str = "") -> None:
    _emit(api_surface_markdown(module), output, module.rsplit(".", 1)[-1], "module")


@tasks.script(
    task_name="api:directory",
    help="Write every module under a directory as one markdown API surface",
    task_args=False,
    options={
        "args": [
            *_surface_args("directory", "Directory of modules to walk"),
            *_path_args(),
        ]
    },
    tags=["docs"],
)
def api_directory(
    directory: str, *, output: str = "", exclude: Sequence[str] = ()
) -> None:
    _emit(
        directory_surface_markdown(directory, exclude),
        output,
        Path(directory).resolve().name,
        "directory",
    )


@tasks.script(
    task_name="api:package",
    help="Write each package's whole API surface to its own markdown file",
    task_args=False,
    options={
        "args": [
            *_surface_args(
                "package",
                "Installed package name or a path in one; "
                "defaults to every workspace member and the frontend",
                required=False,
            ),
            *_path_args(),
        ]
    },
    tags=["docs"],
)
def api_package(
    package: str = "", *, output: str = "", exclude: Sequence[str] = ()
) -> None:
    if package and package != FRONTEND_PACKAGE:
        targets = [resolve_package(package)]
    elif output:
        raise ValueError(
            f"--output needs a single Python package; {FRONTEND_PACKAGE} and "
            "the whole workspace write to docs/"
        )
    else:
        targets = [] if package else workspace_packages()
    if package in ("", FRONTEND_PACKAGE):
        frontend_api_surface()
    for name, directory in targets:
        _emit(
            directory_surface_markdown(
                str(directory), exclude, title=name, heading_base=directory
            ),
            output,
            name,
            "package",
        )


@tasks.script(
    task_name="joke",
    help="Ask the configured Azure Responses model for a one-line joke",
    tags=["llm"],
)
def joke(topic: str = "oil and gas data") -> None:
    responses_joke(topic)
