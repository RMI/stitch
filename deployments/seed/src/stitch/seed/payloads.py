from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


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


def iter_payloads(count: int) -> Iterable[dict[str, Any]]:
    for i in range(1, count + 1):
        yield build_payload(i)
