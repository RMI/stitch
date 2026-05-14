from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
import os


from typing import Any

import httpx

from .config import StitchClientConfig
from .errors import StitchAuthError

STITCH_CLIENT_BEARER_TOKEN_ENV_VAR = "STITCH_CLIENT_BEARER_TOKEN"


async def fetch_auth_jwt(
    config: StitchClientConfig,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """POST client-credentials to Auth0 and return the access_token string."""
    payload = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "audience": config.audience,
        "grant_type": "client_credentials",
    }
    async with httpx.AsyncClient(
        base_url=config.auth_issuer_url,
        transport=transport,
        timeout=30.0,
    ) as auth_client:
        try:
            res = await auth_client.post("/oauth/token", json=payload)
        except httpx.HTTPError as exc:
            raise StitchAuthError(f"Auth0 token request failed: {exc}") from exc

    if res.status_code != 200:
        raise StitchAuthError(
            f"Auth0 token request returned status {res.status_code}",
            status_code=res.status_code,
            response_text=res.text,
        )
    try:
        body = res.json()
    except ValueError as exc:
        raise StitchAuthError(
            "Auth0 token response was not valid JSON",
            status_code=res.status_code,
            response_text=res.text,
        ) from exc
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        raise StitchAuthError(
            "Auth0 token response missing 'access_token'",
            status_code=res.status_code,
            response_text=res.text,
        )
    return token


TokenFetcher = Callable[[], Awaitable[str]]


class Auth0M2MAuth(httpx.Auth):
    requires_response_body = True

    def __init__(self, token_fetcher: TokenFetcher) -> None:
        self._token_fetcher = token_fetcher
        self._token: str | None = None
        self._lock = asyncio.Lock()

    async def _ensure_token(self, *, force: bool = False) -> str:
        async with self._lock:
            if force or self._token is None:
                self._token = await self._token_fetcher()
            return self._token

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        token = await self._ensure_token()
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request

        if response.status_code != 401:
            return

        await response.aread()
        token = await self._ensure_token(force=True)
        request.headers["Authorization"] = f"Bearer {token}"
        yield request

    def sync_auth_flow(self, request: httpx.Request) -> Any:  # pragma: no cover
        raise RuntimeError("Auth0M2MAuth only supports async usage")


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
