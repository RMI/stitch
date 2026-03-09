#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path


def find_package_dir(name: str) -> str:
    root = tomllib.loads(Path("pyproject.toml").read_text())
    for member in root["tool"]["uv"]["workspace"]["members"]:
        p = Path(member) / "pyproject.toml"
        if p.exists() and tomllib.loads(p.read_text())["project"]["name"] == name:
            return member
    print(f"error: package {name!r} not found in workspace", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run pytest for a uv workspace package.",
    )
    parser.add_argument("package", help="workspace package name")
    parser.add_argument(
        "--exact",
        action="store_true",
        help="install only the package's declared deps (CI isolation)",
    )
    known, pytest_args = parser.parse_known_args()

    pkg_dir = find_package_dir(known.package)

    cmd = ["uv", "run", "--package", known.package]
    if known.exact:
        cmd += ["--exact", "--group", "dev"]
    cmd += ["pytest", pkg_dir, *pytest_args]

    sys.exit(subprocess.call(cmd))


main()
