import logging
import os
from dataclasses import dataclass


logger = logging.getLogger("stitch.seed")


def env_int(name: str, default: int | None) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not an int; using %s", name, raw, default)
        return default


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("%s=%r is not a float; using %s", name, raw, default)
        return default


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


@dataclass(frozen=True)
class SeedConfig:
    api_base_url: str
    faker_post_count: int | None
    http_timeout_seconds: float
    static_payload_dir: str | None
    random_seed: int | None
    seed_source: str
    null_probability: float
    # --- Complexity knobs (default off => legacy single-source behavior) ---
    # When true, `mixed` draws source keys from all 8 OGSI sources (adds
    # ccr/alb/bc/nor) instead of only gem/wm/rmi/llm. Useful when a comparison
    # must exercise every source key (e.g. permission profiles keyed on a source).
    all_source_keys: bool
    # Probability a faker resource is built from multiple source records
    # (distinct source keys) in a single create — exercises per-field coalescing.
    multi_source_prob: float
    # Max extra sources beyond the first for a multi-source resource
    # (total sources = 1 + randint(1, max_extra_sources)).
    max_extra_sources: int
    # Probability a created resource gets a field-specific priority override
    # (post-create PUT) — exercises the two-tier per-field ranking.
    override_prob: float
    # Probability a created resource is drawn into a merge (pairs approved
    # post-create via the merge-candidate workflow) — exercises repointed resources.
    merge_prob: float
    # Deterministic offset for cumulative seeding: skip (build-and-discard, so the
    # RNG advances identically) the first N faker payloads and emit N+1..N+count.
    # A run at start_index=K produces the same payloads a fresh count=K+count run
    # would have produced for indices K+1..K+count, so growing a volume rung-by-rung
    # (each row seeded once) stays deterministic and nested. Static payloads are
    # emitted only at start_index=0 to avoid duplicating them on continuation runs.
    start_index: int


def load_config() -> SeedConfig:
    api_base_url = os.getenv("API_BASE_URL", "http://api:8000/api/v1")
    faker_post_count = env_int("FAKER_POST_COUNT", 0)
    http_timeout_seconds = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
    static_payload_dir = os.getenv("STATIC_PAYLOAD_DIR")
    random_seed = env_int("RANDOM_SEED", None)
    seed_source = os.getenv("SEED_SOURCE", "mixed").strip().lower()
    null_probability = env_float("NULL_PROBABILITY", 0.2)
    all_source_keys = env_bool("SEED_ALL_SOURCE_KEYS", False)
    multi_source_prob = env_float("SEED_MULTI_SOURCE_PROB", 0.0)
    max_extra_sources = env_int("SEED_MAX_EXTRA_SOURCES", 0) or 0
    override_prob = env_float("SEED_OVERRIDE_PROB", 0.0)
    merge_prob = env_float("SEED_MERGE_PROB", 0.0)
    start_index = env_int("SEED_START_INDEX", 0) or 0
    return SeedConfig(
        api_base_url=api_base_url,
        faker_post_count=faker_post_count,
        http_timeout_seconds=http_timeout_seconds,
        static_payload_dir=static_payload_dir,
        random_seed=random_seed,
        seed_source=seed_source,
        null_probability=null_probability,
        all_source_keys=all_source_keys,
        multi_source_prob=multi_source_prob,
        max_extra_sources=max_extra_sources,
        override_prob=override_prob,
        merge_prob=merge_prob,
        start_index=start_index,
    )
