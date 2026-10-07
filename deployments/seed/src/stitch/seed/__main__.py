import asyncio
import random

from stitch.client import AsyncStitchClient, env_bearer_token_headers_provider

from .client import post_payloads
from .complexify import complexify
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
        all_source_keys=cfg.all_source_keys,
        multi_source_prob=cfg.multi_source_prob,
        max_extra_sources=cfg.max_extra_sources,
        start_index=cfg.start_index,
    )
    headers_provider = env_bearer_token_headers_provider()
    headers_provider()

    async with AsyncStitchClient(
        base_url=cfg.api_base_url,
        timeout=cfg.http_timeout_seconds,
        headers_provider=headers_provider,
    ) as client:
        await client.wait_for_health()
        created_ids = await post_payloads(client, payloads)

        if cfg.override_prob > 0.0 or cfg.merge_prob > 0.0:
            # Separate RNG stream (seeded from RANDOM_SEED) so the post-create
            # pass is reproducible without perturbing payload generation.
            complexify_rng = random.Random(
                (cfg.random_seed or 0) ^ 0x5EED  # distinct, deterministic stream
            )
            await complexify(
                client,
                created_ids,
                rng=complexify_rng,
                override_prob=cfg.override_prob,
                merge_prob=cfg.merge_prob,
            )

    logger.info("Seed finished successfully")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
