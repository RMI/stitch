from __future__ import annotations

import os
from dataclasses import dataclass

from .errors import StitchAuthError

_REQUIRED_ENV_VARS = (
    "STITCH_AUTH_CLIENT_ID",
    "STITCH_AUTH_CLIENT_SECRET",
    "STITCH_AUTH_AUDIENCE",
    "STITCH_AUTH_ISSUER_URL",
    "STITCH_API_BASE_URL",
)


@dataclass(frozen=True)
class StitchClientConfig:
    client_id: str
    client_secret: str
    audience: str
    auth_issuer_url: str
    api_base_url: str

    @classmethod
    def from_env(cls) -> "StitchClientConfig":
        missing: list[str] = []
        values: dict[str, str] = {}
        for var in _REQUIRED_ENV_VARS:
            v = os.environ.get(var)
            if not v:
                missing.append(var)
            else:
                values[var] = v
        if missing:
            raise StitchAuthError(
                "Missing required environment variable(s) for "
                f"StitchClientConfig.from_env(): {', '.join(missing)}"
            )
        return cls(
            client_id=values["STITCH_AUTH_CLIENT_ID"],
            client_secret=values["STITCH_AUTH_CLIENT_SECRET"],
            audience=values["STITCH_AUTH_AUDIENCE"],
            auth_issuer_url=values["STITCH_AUTH_ISSUER_URL"],
            api_base_url=values["STITCH_API_BASE_URL"],
        )
