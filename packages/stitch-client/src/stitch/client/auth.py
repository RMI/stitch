from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

import httpx

from .config import StitchClientConfig
from .errors import StitchAuthError


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


async def validate_downstream_auth_at_startup(
    *,
    api_base_url: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Fail fast at boot if Auth0 M2M credentials are present but broken.

    No-op when the service is unconfigured for M2M (``from_partial_env`` returns
    ``None`` → the no-header path). When configured, performs one
    client-credentials token fetch so bad ``STITCH_AUTH_*`` credentials surface
    as a clear ``StitchAuthError`` at startup rather than as an opaque 401 on
    the first real request.

    ``transport`` is a test seam (forwarded to ``fetch_auth_jwt``); callers pass
    only ``api_base_url``.
    """
    config = StitchClientConfig.from_partial_env(api_base_url=api_base_url)
    if config is None:
        return
    await fetch_auth_jwt(config, transport=transport)


TokenFetcher = Callable[[], Awaitable[str]]


class Auth0M2MAuth(httpx.Auth):
    requires_response_body = True

    def __init__(self, token_fetcher: TokenFetcher) -> None:
        self._token_fetcher = token_fetcher
        self._token: str | None = None
        self._lock = asyncio.Lock()

    async def _ensure_token(self, *, force_if_stale: str | None = None) -> str:
        """Return a cached token, fetching a new one only when necessary.

        Double-checked locking keyed on the stale token the caller observed:
        refetch only if there is no token yet, or the cached token still equals
        the stale one the caller saw. When N in-flight requests all 401 off the
        same stale token, the first refetch rotates the cache and the rest
        observe the fresh token — so the token endpoint is hit once, not N
        times (no thundering herd).
        """
        async with self._lock:
            is_stale = force_if_stale is not None and self._token == force_if_stale
            if self._token is None or is_stale:
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
        token = await self._ensure_token(force_if_stale=token)
        request.headers["Authorization"] = f"Bearer {token}"
        yield request

    def sync_auth_flow(self, request: httpx.Request) -> Any:  # pragma: no cover
        raise RuntimeError("Auth0M2MAuth only supports async usage")
