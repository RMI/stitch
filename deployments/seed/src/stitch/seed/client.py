from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from stitch.client import AsyncStitchClient


logger = logging.getLogger("stitch.seed")


async def post_payloads(
    client: AsyncStitchClient,
    payloads: Iterable[dict[str, Any]],
) -> list[int]:
    """POST each payload, returning the ids of the created resources (in order).

    The ids feed the optional post-create complexifier (field-priority overrides
    and merges); callers that don't complexify can ignore the return value.
    """
    created_ids: list[int] = []
    for payload in payloads:
        logger.debug("Payload: %s", json.dumps(payload, ensure_ascii=False))

        response = await client.create_oil_gas_field(payload)
        logger.info("Response status=success")

        logger.debug(
            "Response body=%s",
            json.dumps(response, ensure_ascii=False),
        )

        resource_id = response.get("id") if isinstance(response, dict) else None
        if isinstance(resource_id, int):
            created_ids.append(resource_id)
    return created_ids
