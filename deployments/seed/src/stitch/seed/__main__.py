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
    logger.info("POST_COUNT=%s", cfg.post_count)

    validator = OpenAPIRequestValidator(cfg.api_base_url, openapi_url=cfg.openapi_url)
    payloads = iter_payloads(cfg.post_count)

    with httpx.Client(timeout=cfg.http_timeout_seconds) as client:
        post_payloads(client, cfg.api_base_url, payloads, validator)

    logger.info("Seed finished successfully")


if __name__ == "__main__":
    main()
