import httpx
from .client import post_payloads
from .config import configure_logging, load_config, logger
from .openapi_validate import OpenAPIRequestValidator
from .payloads import iter_payloads


def main() -> None:
    configure_logging()
    cfg = load_config()

    logger.info("Seed starting")
    logger.info("API_BASE_URL=%s", cfg.api_base_url)
    logger.info("POST_COUNT=%s", cfg.faker_post_count)

    validator = OpenAPIRequestValidator(cfg.api_base_url, openapi_url=cfg.openapi_url)
    payloads = iter_payloads(
        static_payload_dir=cfg.static_payload_dir,
        faker_count=cfg.faker_post_count,
        random_seed=cfg.random_seed,
        seed_source=cfg.seed_source,
        null_prob=cfg.null_probability,
    )

    with httpx.Client(timeout=cfg.http_timeout_seconds) as client:
        post_payloads(client, cfg.api_base_url, payloads, validator)

    logger.info("Seed finished successfully")


if __name__ == "__main__":
    main()
