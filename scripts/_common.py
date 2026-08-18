"""Shared helpers for the throwaway duplicate-hunting scripts.

Not shipped code, not committed. See scripts/README.md for the workflow.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
DATA_DIR = SCRIPTS_DIR / "data"
RESOURCES_PATH = DATA_DIR / "resources.jsonl"
CANDIDATES_PATH = DATA_DIR / "candidates.json"

DEFAULT_BASE_URL = (
    "https://pr-0242-demo-batch-ai-3ae8-api.salmonsea-0e166cd2."
    "westus2.azurecontainerapps.io/api/v1"
)


def load_dotenv(path: Path | None = None) -> None:
    """Populate os.environ from .env without overriding what is already set."""
    env_path = path if path is not None else REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def base_url() -> str:
    load_dotenv()
    return os.getenv("STITCH_API_BASE_URL") or DEFAULT_BASE_URL


def auth_headers() -> dict[str, str]:
    """Bearer header from the privileged token. The token is never printed."""
    load_dotenv()
    token = os.getenv("STITCH_CLIENT_PRIVILEGED_BEARER_TOKEN") or os.getenv(
        "STITCH_CLIENT_BEARER_TOKEN"
    )
    if not token:
        raise SystemExit(
            "no bearer token: set STITCH_CLIENT_PRIVILEGED_BEARER_TOKEN in .env"
        )
    return {"Authorization": f"Bearer {token}"}


def distinct_sources(provenance: dict[str, Any] | None) -> list[str]:
    """The set of source keys that won at least one field on a resource."""
    if not provenance:
        return []
    return sorted({value for value in provenance.values() if isinstance(value, str)})


def flatten_list_item(item: dict[str, Any]) -> dict[str, Any]:
    """Project an OGFieldListItemView down to the fields the matcher needs."""
    data = item.get("data") or {}
    return {
        "id": item["id"],
        "name": data.get("name"),
        "country": data.get("country"),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "name_local": data.get("name_local"),
        "state_province": data.get("state_province"),
        "region": data.get("region"),
        "basin": data.get("basin"),
        "operators": [
            operator.get("name")
            for operator in (data.get("operators") or [])
            if isinstance(operator, dict)
        ],
        "owners": [
            owner.get("name")
            for owner in (data.get("owners") or [])
            if isinstance(owner, dict)
        ],
        "field_status": data.get("field_status"),
        "sources": distinct_sources(item.get("provenance")),
    }
