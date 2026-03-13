from __future__ import annotations

import logging
import random
from typing import Any, Iterable, get_args, Iterator

from faker import Faker

import json
from pathlib import Path

from stitch.ogsi.model.types import (
    FieldStatus,
    LocationType,
    PrimaryHydrocarbonGroup,
    ProductionConventionality,
)

logger = logging.getLogger("stitch.seed")


def _seed(random_seed: int | None) -> int | None:
    if random_seed is None:
        return None
    return int(random_seed)


def _source_key(seed_source: str, rng: random.Random) -> str:
    """
    Choose which discriminator `source` to use in source_data.
    Env: SEED_SOURCE=gem|wm|rmi|llm|mixed
    """
    if seed_source == "mixed":
        return rng.choice(["gem", "wm", "rmi", "llm"])
    if seed_source in {"gem", "wm", "rmi", "llm"}:
        return seed_source
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


def _null_probability(prob) -> float:
    try:
        p = float(prob)
    except ValueError:
        p = 0.2
    return max(0.0, min(1.0, p))


def _maybe(value_fn, *, rng: random.Random, allow_null: bool = True, null_prob: float):
    """
    value_fn: callable producing a value
    Returns None with probability NULL_PROBABILITY if allow_null=True.
    """
    if allow_null and rng.random() < _null_probability(null_prob):
        return None
    return value_fn()


def build_og_field(
    *, fake: Faker, seed_source: str, rng: random.Random, null_prob: float
) -> dict[str, Any]:
    country = fake.country_code(representation="alpha-3")
    name = _fake_companyish(fake, rng)

    discovery_year, production_start_year, fid_year = _year_triplet(rng)

    return {
        # REQUIRED
        "name": name,
        "country": country,
        # OPTIONAL — allow None
        "latitude": _maybe(
            lambda: float(fake.latitude()), rng=rng, null_prob=null_prob
        ),
        "longitude": _maybe(
            lambda: float(fake.longitude()), rng=rng, null_prob=null_prob
        ),
        "name_local": _maybe(
            lambda: " ".join(fake.words()).title(), rng=rng, null_prob=null_prob
        ),
        "state_province": _maybe(lambda: fake.state(), rng=rng, null_prob=null_prob),
        "region": _maybe(lambda: fake.city(), rng=rng, null_prob=null_prob),
        "basin": _maybe(
            lambda: f"{fake.word().title()} Basin", rng=rng, null_prob=null_prob
        ),
        "owners": None,  # leave structural fields alone for now
        "operators": None,
        "location_type": _maybe(
            lambda: rng.choice(list(get_args(LocationType))),
            rng=rng,
            null_prob=null_prob,
        ),
        "production_conventionality": _maybe(
            lambda: rng.choice(list(get_args(ProductionConventionality))),
            rng=rng,
            null_prob=null_prob,
        ),
        "primary_hydrocarbon_group": _maybe(
            lambda: rng.choice(list(get_args(PrimaryHydrocarbonGroup))),
            rng=rng,
            null_prob=null_prob,
        ),
        "reservoir_formation": _maybe(
            lambda: f"{fake.word().title()} Formation", rng=rng, null_prob=null_prob
        ),
        "discovery_year": discovery_year,
        "production_start_year": production_start_year,
        "fid_year": fid_year,
        "field_status": _maybe(
            lambda: rng.choice(list(get_args(FieldStatus))),
            rng=rng,
            null_prob=null_prob,
        ),
        "source": _source_key(seed_source=seed_source, rng=rng),
    }


def build_payload(
    *, fake: Faker, seed_source: str, rng: random.Random, null_prob: float
) -> dict[str, Any]:
    """
    POST body is Resource-Input (OpenAPI), which requires id.
    """
    src = build_og_field(
        fake=fake, seed_source=seed_source, rng=rng, null_prob=null_prob
    )

    return {
        "id": 0,
        "source_data": [src],
        "constituents": [],
    }


def _iter_static_payloads(static_payload_dir: str) -> Iterator[dict[str, Any]]:
    """
    Load JSON payloads from a directory.
    Each file may be either:
      - a single payload object, or
      - a list of payload objects.
    Files are consumed in sorted(path) order for reproducibility.
    """
    base = Path(static_payload_dir)
    if not base.exists():
        logger.warning("STATIC_PAYLOAD_DIR does not exist: %s", static_payload_dir)
        return
    if not base.is_dir():
        logger.warning("STATIC_PAYLOAD_DIR is not a directory: %s", static_payload_dir)
        return

    paths = sorted(p for p in base.glob("*.json") if p.is_file())
    if not paths:
        logger.info("No static payload files found in %s", static_payload_dir)
        return

    logger.info(
        "Loading %d static payload file(s) from %s", len(paths), static_payload_dir
    )
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed reading static payload file: %s", path)
            continue

        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    yield item
                else:
                    logger.warning(
                        "Skipping non-object item in %s: %r", path, type(item).__name__
                    )
        elif isinstance(raw, dict):
            yield raw
        else:
            logger.warning(
                "Skipping %s: expected object or list, got %r", path, type(raw).__name__
            )


def iter_payloads(
    static_payload_dir: str | None,
    faker_count: int | None,
    random_seed: int | None,
    seed_source: str,
    null_prob: float,
) -> Iterable[dict[str, Any]]:
    seed = _seed(random_seed)
    rng = random.Random(seed)
    fake = Faker()
    if seed is not None:
        Faker.seed(seed)

    if static_payload_dir is not None:
        yield from _iter_static_payloads(static_payload_dir)

    if faker_count is not None and faker_count > 0:
        for i in range(1, faker_count + 1):
            yield build_payload(
                fake=fake, seed_source=seed_source, rng=rng, null_prob=null_prob
            )
