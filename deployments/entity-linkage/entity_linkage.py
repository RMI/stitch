import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict
from urllib.parse import urljoin, urlparse

import httpx


@dataclass(frozen=True)
class Config:
    api_url: str
    sleep_seconds: float
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    log_level: str

    @staticmethod
    def from_env() -> "Config":
        api_url = os.getenv("API_URL", "").strip()
        if not api_url:
            raise ValueError("API_URL must be set (e.g. http://api:8000)")

        parsed = urlparse(api_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"API_URL must be a valid http(s) URL; got: {api_url!r}")

        def get_float(name: str, default: str) -> float:
            raw = os.getenv(name, default).strip()
            return float(raw)

        def get_int(name: str, default: str) -> int:
            raw = os.getenv(name, default).strip()
            return int(raw)

        return Config(
            api_url=api_url.rstrip("/") + "/",
            sleep_seconds=get_float("ENTITY_LINKAGE_SLEEP_SECONDS", "10"),
            timeout_seconds=get_float("ENTITY_LINKAGE_TIMEOUT_SECONDS", "10"),
            max_retries=get_int("ENTITY_LINKAGE_MAX_RETRIES", "60"),
            retry_backoff_seconds=get_float("ENTITY_LINKAGE_RETRY_BACKOFF_SECONDS", "1"),
            log_level=os.getenv("ENTITY_LINKAGE_LOG_LEVEL", "INFO").strip().upper(),
        )


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


log = logging.getLogger("entity-linkage")


def _safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return "<unserializable>"


def wait_for_api(cfg: Config) -> None:
    """
    Minimal readiness probe: repeatedly GET health (preferred),
    else fall back to GET resources/ if health isn't present.
    """
    candidates = [
        urljoin(cfg.api_url, "health"),
        urljoin(cfg.api_url, "resources/"),
    ]

    timeout = httpx.Timeout(cfg.timeout_seconds)
    with httpx.Client(timeout=timeout) as client:
        for attempt in range(1, cfg.max_retries + 1):
            for url in candidates:
                try:
                    r = client.get(url)
                    if 200 <= r.status_code < 500:
                        # 2xx/3xx means good, 4xx means server is up even if route differs.
                        log.info("API reachable: %s (status=%s)", url, r.status_code)
                        return
                    log.warning(
                        "API not ready yet: %s (status=%s, body=%s)",
                        url,
                        r.status_code,
                        r.text[:300],
                    )
                except Exception as e:
                    log.warning("API probe failed: %s (%s)", url, e)

            if attempt < cfg.max_retries:
                time.sleep(cfg.retry_backoff_seconds)

    raise RuntimeError(
        f"API not reachable after {cfg.max_retries} retries; last tried: {candidates}"
    )


def do_get_then_post(cfg: Config) -> None:
    """
    Stub logic:
      1) GET resources/
      2) POST resources/ with a dummy payload

    If your API contract changes, this is the only place you should need to edit.
    """
    timeout = httpx.Timeout(cfg.timeout_seconds)

    get_url = urljoin(cfg.api_url, "resources/")
    post_url = urljoin(cfg.api_url, "resources/")

    payload: Dict[str, Any] = {
        "name": "entity-linkage-stub",
        "country": "XYZ",
        "repointed_to": None,
        "source_data": None
    }

    with httpx.Client(timeout=timeout) as client:
        log.info("GET %s", get_url)
        r_get = client.get(get_url)
        log.info(
            "GET response status=%s headers=%s body=%s",
            r_get.status_code,
            dict(r_get.headers),
            r_get.text[:1000],
        )

        log.info("POST %s payload=%s", post_url, _safe_json(payload))
        r_post = client.post(post_url, json=payload)
        log.info(
            "POST response status=%s headers=%s body=%s",
            r_post.status_code,
            dict(r_post.headers),
            r_post.text[:1000],
        )

        # Raise on unexpected server errors, but keep stubbing friendly
        if r_get.status_code >= 500:
            raise RuntimeError(f"GET failed with status {r_get.status_code}")
        if r_post.status_code >= 500:
            raise RuntimeError(f"POST failed with status {r_post.status_code}")


def main() -> int:
    try:
        cfg = Config.from_env()
    except Exception as e:
        print(f"[entity-linkage] config error: {e}", file=sys.stderr)
        return 2

    setup_logging(cfg.log_level)
    log.info(
        "Starting (api_url=%s, sleep=%ss)",
        cfg.api_url,
        cfg.sleep_seconds,
    )

    try:
        wait_for_api(cfg)
    except Exception:
        log.exception("API did not become reachable")
        return 3

    while True:
        start = time.time()
        try:
            do_get_then_post(cfg)
            log.info("Iteration ok (elapsed=%.2fs). Sleeping %ss.", time.time() - start, cfg.sleep_seconds)
        except Exception:
            log.exception("Iteration failed. Sleeping %ss.", cfg.sleep_seconds)

        time.sleep(cfg.sleep_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
