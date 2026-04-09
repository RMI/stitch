from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from subprocess import CalledProcessError, run


REPO_ROOT = Path(__file__).resolve().parents[5]


@dataclass(frozen=True)
class BuildInfo:
    app_version: str
    build_id: str
    git_sha: str
    build_time: str


def _run_git(*args: str) -> str | None:
    try:
        completed = run(
            ["git", *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (CalledProcessError, FileNotFoundError):
        return None

    value = completed.stdout.strip()
    return value or None


def _get_app_version() -> str:
    try:
        return package_version("stitch-api")
    except PackageNotFoundError:
        return "unknown"


@lru_cache
def get_build_info() -> BuildInfo:
    git_sha = _run_git("rev-parse", "HEAD") or "unknown"
    short_sha = _run_git("rev-parse", "--short", "HEAD") or git_sha[:7] or "unknown"

    return BuildInfo(
        app_version=_get_app_version(),
        build_id=short_sha,
        git_sha=git_sha,
        build_time=datetime.now(UTC).isoformat(),
    )
