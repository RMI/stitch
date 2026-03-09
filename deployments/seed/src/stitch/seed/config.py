import logging
import os
from dataclasses import dataclass


logger = logging.getLogger("stitch.seed")


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
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
    post_count: int
    http_timeout_seconds: float
    openapi_url: str | None


def load_config() -> SeedConfig:
    api_base_url = os.getenv("API_BASE_URL", "http://api:8000/api/v1")
    post_count = env_int("POST_COUNT", 5)
    http_timeout_seconds = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
    openapi_url = os.getenv("OPENAPI_URL")  # optional override
    return SeedConfig(
        api_base_url=api_base_url,
        post_count=post_count,
        http_timeout_seconds=http_timeout_seconds,
        openapi_url=openapi_url,
    )
