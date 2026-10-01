"""The candidate-groups file that the merge workflow scripts hand to each other."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import data_dir

RESOURCES_PATH = data_dir() / "resources.jsonl"
CANDIDATES_PATH = data_dir() / "candidates.json"

CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


def load_payload(path: Path | str) -> dict[str, Any]:
    """Read the whole candidates file, params and groups together."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_payload(path: Path | str, payload: dict[str, Any]) -> None:
    """Write the candidates file back in the one format every reader expects."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def member_names(group: dict[str, Any]) -> str:
    """The names in one group on a single line, for review output."""
    return " || ".join(member["name"] or "" for member in group["members"])
