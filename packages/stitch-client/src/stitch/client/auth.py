from __future__ import annotations

import os
from collections.abc import Callable

STITCH_CLIENT_BEARER_TOKEN_ENV_VAR = "STITCH_CLIENT_BEARER_TOKEN"


def env_bearer_token_headers_provider() -> Callable[[], dict[str, str]]:
    """
    Build a headers provider backed by STITCH_CLIENT_BEARER_TOKEN.
    """

    def provider() -> dict[str, str]:
        token = os.getenv(STITCH_CLIENT_BEARER_TOKEN_ENV_VAR, "").strip()
        if not token:
            raise ValueError(f"{STITCH_CLIENT_BEARER_TOKEN_ENV_VAR} must be set")
        return {"Authorization": f"Bearer {token}"}

    return provider
