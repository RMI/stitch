"""Load the env files these scripts share, most specific first."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from .paths import repo_root

# Most specific first. Nothing already set is overwritten, so an earlier file
# wins and the repo-wide `.env` still supplies whatever the others leave unset.
DEFAULT_ENV_FILES = (".env.scripts", "scripts/.env", ".env")


def load_script_env(
    *extra: Path | str,
    root: Path | None = None,
) -> list[Path]:
    """Load env files into ``os.environ``; return those that existed, in load order.

    Precedence, highest first: variables already exported in the environment,
    then each path in ``extra`` in the order given, then ``DEFAULT_ENV_FILES``.
    Because no file overwrites a value that is already set, this load order
    *is* the precedence chain.

    Relative paths resolve against the repo root, so callers need not know
    where they were invoked from.
    """
    base = root or repo_root()
    loaded: list[Path] = []

    for raw in (*extra, *DEFAULT_ENV_FILES):
        candidate = Path(raw)
        path = candidate if candidate.is_absolute() else base / candidate
        if path.is_file():
            # override=False is the default; stated here because the whole
            # precedence model depends on it.
            load_dotenv(path, override=False)
            loaded.append(path)

    return loaded
