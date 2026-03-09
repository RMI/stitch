import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[seed] WARN: {name}={raw!r} is not an int; using {default}")
        return default


def build_og_field() -> dict[str, Any]:
    return {
        "name": "turquoise 1080p hard drive",
        "country": "XPG",
        "latitude": 70.0823,
        "longitude": -138.7758,
        "name_local": "Aufderhar LLC 516",
        "state_province": "Tromp, Romaguera and Macejkovic 42",
        "region": "McGlynn - Russel 194",
        "basin": "Wolf LLC 878",
        "owners": None,
        "operators": None,
        "location_type": "Offshore",
        "production_conventionality": "Mixed",
        "primary_hydrocarbon_group": "Light Oil",
        "reservoir_formation": "Lueilwitz, Haag and Strosin 333",
        "discovery_year": 1801,
        "production_start_year": 1802,
        "fid_year": 1803,
        "field_status": "Producing",
        "source": "gem",
    }


def build_payload(i: int) -> dict[str, Any]:
    """
    PR #32 currently defines POST /oil-gas-fields with body model `Resource`,
    which requires an `id: int` plus optional name/country. We'll send id=0
    and let the server decide what to do with it.
    """
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return {
        "id": 0,
        "name": f"seeded-og-field-{now}-{i}",
        "country": None,
        "source_data": [build_og_field()],
        "constituents": [],
    }


def post_once(client: httpx.Client, base_url: str, i: int) -> None:
    url = f"{base_url.rstrip('/')}/oil-gas-fields/"
    payload = build_payload(i)
    print(f"[seed] POST {url}")
    print(f"[seed] payload={json.dumps(payload, ensure_ascii=False)}")

    resp = client.post(url, json=payload)
    print(f"[seed] status={resp.status_code}")
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    print(
        f"[seed] response={json.dumps(body, ensure_ascii=False) if isinstance(body, (dict, list)) else body}"
    )

    resp.raise_for_status()


def main() -> None:
    base_url = os.getenv("API_BASE_URL", "http://api:8000/api/v1")
    post_count = _env_int("POST_COUNT", 5)
    timeout_seconds = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))

    print("[seed] starting")
    print(f"[seed] API_BASE_URL={base_url}")

    with httpx.Client(timeout=timeout_seconds) as client:
        for i in range(1, post_count + 1):
            post_once(client, base_url, i)

    print("[seed] done")


if __name__ == "__main__":
    main()
