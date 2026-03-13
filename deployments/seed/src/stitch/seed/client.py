from __future__ import annotations

import json
import logging
from typing import Any, Iterable

import httpx

from .openapi_validate import OpenAPIRequestValidator


logger = logging.getLogger("stitch.seed")


def post_payloads(
    client: httpx.Client,
    api_base_url: str,
    payloads: Iterable[dict[str, Any]],
    validator: OpenAPIRequestValidator,
) -> None:
    url = f"{api_base_url.rstrip('/')}/oil-gas-fields/"

    for payload in payloads:
        validator.validate(payload, client)
        logger.info("POST %s", url)
        logger.debug("Payload: %s", json.dumps(payload, ensure_ascii=False))

        resp = client.post(url, json=payload)
        logger.info("Response status=%s", resp.status_code)

        # body is debug-level (often large)
        try:
            body: Any = resp.json()
        except Exception:
            body = resp.text
        logger.debug(
            "Response body=%s",
            json.dumps(body, ensure_ascii=False)
            if isinstance(body, (dict, list))
            else body,
        )

        resp.raise_for_status()
