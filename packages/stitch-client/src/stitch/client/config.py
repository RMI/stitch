from __future__ import annotations

import os
from dataclasses import dataclass

from .errors import StitchAuthError

# The four Auth0 M2M (client-credentials) variables. The base URL is supplied
# by the caller (each service keeps its own base-url env var), so it is not part
# of this set.
_M2M_ENV_VARS = (
    "STITCH_AUTH_CLIENT_ID",
    "STITCH_AUTH_CLIENT_SECRET",
    "STITCH_AUTH_AUDIENCE",
    "STITCH_AUTH_ISSUER_URL",
)

_REQUIRED_ENV_VARS = (*_M2M_ENV_VARS, "STITCH_API_BASE_URL")


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

    @classmethod
    def from_partial_env(cls, *, api_base_url: str) -> "StitchClientConfig | None":
        """Build M2M config from the four ``STITCH_AUTH_*`` vars, or ``None``.

        This is the config-selected auth switch used by deployed services:

        - **All four absent** → returns ``None``; the caller attaches no
          ``Authorization`` header (works against a local ``AUTH_DISABLED`` API,
          fails loud with 401 against a real API).
        - **All four present** → returns a config using the caller-supplied
          ``api_base_url`` (each service keeps its own base-url env var, so
          ``STITCH_API_BASE_URL`` is intentionally not read here).
        - **Partially set** → raises ``StitchAuthError``; a half-config is a
          typo/misconfiguration and must fail loud rather than silently fall
          back to the no-header path.
        """
        values = {var: (os.environ.get(var) or "") for var in _M2M_ENV_VARS}
        present = [var for var, value in values.items() if value]
        if not present:
            return None
        missing = [var for var in _M2M_ENV_VARS if not values[var]]
        if missing:
            raise StitchAuthError(
                "Incomplete Auth0 M2M configuration: set all of "
                f"{', '.join(_M2M_ENV_VARS)} or none. "
                f"Missing: {', '.join(missing)}"
            )
        return cls(
            client_id=values["STITCH_AUTH_CLIENT_ID"],
            client_secret=values["STITCH_AUTH_CLIENT_SECRET"],
            audience=values["STITCH_AUTH_AUDIENCE"],
            auth_issuer_url=values["STITCH_AUTH_ISSUER_URL"],
            api_base_url=api_base_url,
        )
