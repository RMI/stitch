#!/usr/bin/env python
"""Regenerate the `## Scripts` section of HACKING.md from each script's --help."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

from lib.paths import repo_root, scripts_dir

HELP_TIMEOUT = 60

HEADING = "## Scripts"
NEXT_HEADING = "## "


def summary(path) -> str:
    """The first line of the module docstring, or a placeholder."""
    doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
    return doc.splitlines()[0].strip() if doc else "_no docstring_"


def usage(path) -> str | None:
    """The argparse usage block on one line, or None without a --help."""
    try:
        result = subprocess.run(
            [sys.executable, path.name, "--help"],
            cwd=path.parent,
            capture_output=True,
            text=True,
            env={**os.environ, "COLUMNS": "200"},
            timeout=HELP_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print(f"    timed out after {HELP_TIMEOUT}s", file=sys.stderr)
        return None
    if result.returncode != 0:
        return None

    block = result.stdout.partition("usage:")[2].partition("\n\n")[0]
    return " ".join(block.split()).replace("[-h] ", "") or None


def render(paths) -> str:
    """The whole section, heading included."""
    lines = [
        HEADING,
        "",
        "All scripts can be called with `uv run --script path/to/<script>.py`. Use `--help` to see usage.",
        "",
    ]
    for path in paths:
        lines.append(f"- **`{path.name}`** — {summary(path)}")
        line = usage(path)
        if line:
            lines.append(f"  `{line}`")
    return "\n".join(lines)


def splice(doc: str, block: str) -> str:
    """Replace the section up to the next `## ` heading, or append it when absent."""
    lines = doc.splitlines()
    start = next((n for n, line in enumerate(lines) if line.rstrip() == HEADING), None)
    if start is None:
        return doc.rstrip() + "\n\n" + block + "\n"

    stop = next(
        (n for n in range(start + 1, len(lines)) if lines[n].startswith(NEXT_HEADING)),
        len(lines),
    )
    spliced = [*lines[:start], *block.splitlines(), "", *lines[stop:]]
    return "\n".join(spliced).rstrip() + "\n"


def main() -> int:
    target = repo_root() / "HACKING.md"
    this = Path(__file__).resolve()
    paths = sorted(
        p
        for p in scripts_dir().glob("*.py")
        if not p.name.startswith("_") and p.resolve() != this
    )

    for path in paths:
        print(f"  {path.name}", file=sys.stderr)

    target.write_text(
        splice(target.read_text(encoding="utf-8"), render(paths)), encoding="utf-8"
    )
    print(f"\nwrote {len(paths)} script(s) to {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
