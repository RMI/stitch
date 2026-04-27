import asyncio

from stitch.client import AsyncStitchClient

from .client import post_payloads
from .config import configure_logging, load_config, logger
from .payloads import iter_payloads


async def run() -> None:
    configure_logging()
    cfg = load_config()

    logger.info("Seed starting")
    logger.info("API_BASE_URL=%s", cfg.api_base_url)
    logger.info("FAKER_POST_COUNT=%s", cfg.faker_post_count)

    payloads = iter_payloads(
        static_payload_dir=cfg.static_payload_dir,
        faker_count=cfg.faker_post_count,
        random_seed=cfg.random_seed,
        seed_source=cfg.seed_source,
        null_prob=cfg.null_probability,
    )

    # TODO: If client/server version skew becomes a real problem, add contract
    # drift checks in CI or integration tests instead of fetching OpenAPI at
    # runtime inside this seeding process.
    async with AsyncStitchClient(
        base_url=cfg.api_base_url,
        timeout=cfg.http_timeout_seconds,
    ) as client:
        await client.wait_for_health()
        await post_payloads(client, payloads)

    logger.info("Seed finished successfully")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
