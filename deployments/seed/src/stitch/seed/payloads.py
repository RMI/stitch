from __future__ import annotations

import os
import random
from typing import Any, Iterable, get_args

from faker import Faker

import json
from pathlib import Path

from stitch.ogsi.model.types import (
    FieldStatus,
    LocationType,
    PrimaryHydrocarbonGroup,
    ProductionConventionality,
)


def _load_static_payloads() -> list[dict[str, Any]]:
    """
    Load static payloads from JSON file.
    File path can be overridden with STATIC_PAYLOAD_FILE env var.
    """
    path_str = os.getenv(
        "STATIC_PAYLOAD_FILE",
        "/mnt/data/static_payloads.json",
    )

    path = Path(path_str)
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    return [d for d in data if isinstance(d, dict)]


def _seed() -> int | None:
    raw = os.getenv("RANDOM_SEED")
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError:
        # Allow non-int seeds too (hash to int).
        return abs(hash(raw)) % (2**31)


def _source_key(rng: random.Random) -> str:
    """
    Choose which discriminator `source` to use in source_data.
    Env: SEED_SOURCE=gem|wm|rmi|llm|mixed
    """
    mode = os.getenv("SEED_SOURCE", "gem").strip().lower()
    if mode == "mixed":
        return rng.choice(["gem", "wm", "rmi", "llm"])
    if mode in {"gem", "wm", "rmi", "llm"}:
        return mode
    return "gem"


def _year_triplet(rng: random.Random) -> tuple[int | None, int | None, int | None]:
    """
    Keep within [1800, 2100] and order roughly: discovery <= start <= fid.
    Allow occasional None to keep variety (schema says years may be nullable).
    """
    if rng.random() < 0.1:
        return None, None, None

    discovery = rng.randint(1800, 2090)
    production_start = min(2100, discovery + rng.randint(0, 20))
    fid = min(2100, production_start + rng.randint(0, 10))
    return discovery, production_start, fid


def _fake_companyish(fake: Faker, rng: random.Random) -> str:
    # Faker company names can be long; keep it a bit field-like.
    base = fake.company().replace(",", "")
    suffix = rng.choice(["Field", "Oil Field", "Gas Field", "Asset"])
    return f"{base} {suffix}"


def _null_probability() -> float:
    raw = os.getenv("NULL_PROBABILITY", "0.2")
    try:
        p = float(raw)
    except ValueError:
        p = 0.2
    return max(0.0, min(1.0, p))


def _maybe(value_fn, *, rng: random.Random, allow_null: bool = True):
    """
    value_fn: callable producing a value
    Returns None with probability NULL_PROBABILITY if allow_null=True.
    """
    if allow_null and rng.random() < _null_probability():
        return None
    return value_fn()


def build_og_field(*, fake: Faker, rng: random.Random) -> dict[str, Any]:
    country = fake.country_code(representation="alpha-3")
    name = _fake_companyish(fake, rng)

    discovery_year, production_start_year, fid_year = _year_triplet(rng)

    return {
        # REQUIRED
        "name": name,
        "country": country,
        # OPTIONAL — allow None
        "latitude": _maybe(lambda: float(fake.latitude()), rng=rng),
        "longitude": _maybe(lambda: float(fake.longitude()), rng=rng),
        "name_local": _maybe(lambda: " ".join(fake.words()).title(), rng=rng),
        "state_province": _maybe(lambda: fake.state(), rng=rng),
        "region": _maybe(lambda: fake.city(), rng=rng),
        "basin": _maybe(lambda: f"{fake.word().title()} Basin", rng=rng),
        "owners": None,  # leave structural fields alone for now
        "operators": None,
        "location_type": _maybe(
            lambda: rng.choice(list(get_args(LocationType))), rng=rng
        ),
        "production_conventionality": _maybe(
            lambda: rng.choice(list(get_args(ProductionConventionality))), rng=rng
        ),
        "primary_hydrocarbon_group": _maybe(
            lambda: rng.choice(list(get_args(PrimaryHydrocarbonGroup))), rng=rng
        ),
        "reservoir_formation": _maybe(
            lambda: f"{fake.word().title()} Formation", rng=rng
        ),
        "discovery_year": discovery_year,
        "production_start_year": production_start_year,
        "fid_year": fid_year,
        "field_status": _maybe(
            lambda: rng.choice(list(get_args(FieldStatus))), rng=rng
        ),
        "source": _source_key(rng),
    }


def build_payload(*, fake: Faker, rng: random.Random) -> dict[str, Any]:
    """
    POST body is Resource-Input (OpenAPI), which requires id.
    Keep payload coherent: top-level name mirrors the first source_data entry.
    """
    src = build_og_field(fake=fake, rng=rng)

    return {
        "id": 0,
        "name": src["name"],
        "source_data": [src],
        "constituents": [],
    }


def iter_payloads(count: int) -> Iterable[dict[str, Any]]:
    seed = _seed()
    rng = random.Random(seed)
    fake = Faker()
    if seed is not None:
        Faker.seed(seed)

    static_payloads = _load_static_payloads()
    for payload in static_payloads:
        yield payload

    for i in range(1, count + 1):
        yield build_payload(fake=fake, rng=rng)
