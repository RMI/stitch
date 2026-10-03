"""Load the env files these scripts share, most specific first."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from .paths import repo_root

DEFAULT_ENV_FILES = (".env.scripts", "scripts/.env", ".env")


def load_script_env(
    *extra: Path | str,
    root: Path | None = None,
) -> list[Path]:
    """Load env files into ``os.environ``; return those that existed, in load order."""
    base = root or repo_root()
    loaded: list[Path] = []

    for raw in (*extra, *DEFAULT_ENV_FILES):
        candidate = Path(raw)
        path = candidate if candidate.is_absolute() else base / candidate
        if path.is_file():
            load_dotenv(path, override=False)
            loaded.append(path)

    return loaded
