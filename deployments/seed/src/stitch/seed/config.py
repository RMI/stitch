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
        logger.warning("%s=%r is not an int; using %s", name, raw, default)
        return default


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
    openapi_url: str | None
    static_payload_dir: str | None
    random_seed: int | None
    seed_source: str
    null_probability: float


def load_config() -> SeedConfig:
    api_base_url = os.getenv("API_BASE_URL", "http://api:8000/api/v1")
    faker_post_count = env_int("FAKER_POST_COUNT", 0)
    http_timeout_seconds = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
    openapi_url = os.getenv("OPENAPI_URL")  # optional override
    static_payload_dir = os.getenv("STATIC_PAYLOAD_DIR")
    random_seed = env_int("RANDOM_SEED", None)
    seed_source = os.getenv("SEED_SOURCE", "mixed").strip().lower()
    null_probability = env_float("NULL_PROBABILITY", 0.2)
    return SeedConfig(
        api_base_url=api_base_url,
        faker_post_count=faker_post_count,
        http_timeout_seconds=http_timeout_seconds,
        openapi_url=openapi_url,
        static_payload_dir=static_payload_dir,
        random_seed=random_seed,
        seed_source=seed_source,
        null_probability=null_probability,
    )
