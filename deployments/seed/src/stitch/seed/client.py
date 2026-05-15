from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from stitch.client import AsyncStitchClient


logger = logging.getLogger("stitch.seed")


async def post_payloads(
    client: AsyncStitchClient,
    payloads: Iterable[dict[str, Any]],
) -> None:

    for payload in payloads:
        logger.debug("Payload: %s", json.dumps(payload, ensure_ascii=False))

        response = await client.create_oil_gas_field(payload)
        logger.info("Response status=success")

        logger.debug(
            "Response body=%s",
            json.dumps(response, ensure_ascii=False),
        )
