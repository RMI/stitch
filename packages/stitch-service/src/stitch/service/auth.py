# NOTE: no `from __future__ import annotations` here. The dependency callables
# built in ServiceAuth.__init__ carry real Annotated objects (Claims/CurrentUser)
# as parameter annotations; stringized annotations would not resolve from the
# closure scope when FastAPI inspects the signature.

import asyncio
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Literal, NoReturn

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from stitch.auth import (
    ALL_PERMISSIONS,
    AuthError,
    InsufficientPermissionsError,
    JWKSFetchError,
    JWTValidator,
    OIDCSettings,
    TokenClaims,
    check_permissions,
)
from stitch.client import env_bearer_token_headers_provider

logger = logging.getLogger("stitch.service.auth")


# --------------------------------------------------------------------------- #
# Identity models
# --------------------------------------------------------------------------- #


class ServiceUser(BaseModel):
    """Lightweight request identity resolved from validated token claims.

    ``id`` defaults to a placeholder; services that need a persisted user row
    supply their own ``user_factory`` to :class:`ServiceAuth`.
    """

    id: int = 1
    sub: str
    email: str
    name: str
    role: str | None = None

    @property
    def label(self) -> str:
        """Human label for attributing actions (e.g. a job's ``initiated_by``)."""
        return self.name or self.email or self.sub


@dataclass(frozen=True, slots=True)
class RequestAuthContext:
    """Request-scoped identity plus the raw caller bearer token.

    The token is retained so a request-scoped (synchronous) service can relay it
    downstream in on-behalf-of mode. Background jobs cannot use it (the request
    is gone by the time the job runs) and should use machine identity instead.
    """

    user: ServiceUser
    bearer_token: str | None


# --------------------------------------------------------------------------- #
# Downstream auth seam — how a service authenticates when calling other services
# --------------------------------------------------------------------------- #


class AuthMode(str, Enum):
    #: Call downstream with the service's own machine identity (env token).
    machine = "machine"
    #: Forward the caller's token downstream unchanged. This is token
    #: *passthrough*, NOT RFC 8693 on-behalf-of: no new token is minted and
    #: nothing records the intermediate hop, so it relies on the downstream
    #: accepting the same token (shared audience). True OBO (token exchange with
    #: an ``act`` actor claim) would be added as a separate mode if needed.
    passthrough = "passthrough"


def machine_token_headers_provider() -> Callable[[], Mapping[str, str]]:
    """Machine identity: bearer token read from the env (STITCH_CLIENT_BEARER_TOKEN)."""
    return env_bearer_token_headers_provider()


def relay_token_headers_provider(token: str) -> Callable[[], Mapping[str, str]]:
    """Passthrough: relay a specific caller token on each downstream request."""
    header = {"Authorization": f"Bearer {token}"}

    def provider() -> Mapping[str, str]:
        return dict(header)

    return provider


def build_headers_provider(
    mode: AuthMode, *, token: str | None = None
) -> Callable[[], Mapping[str, str]]:
    """Build the downstream ``headers_provider`` for the chosen auth mode.

    ``machine`` reads the env token; ``passthrough`` requires ``token`` (the
    caller's bearer token, e.g. ``RequestAuthContext.bearer_token``) and
    forwards it unchanged.
    """
    if mode is AuthMode.machine:
        return machine_token_headers_provider()
    if mode is AuthMode.passthrough:
        if not token:
            raise ValueError("passthrough mode requires a caller token")
        return relay_token_headers_provider(token)
    raise ValueError(f"unknown auth mode: {mode!r}")


# --------------------------------------------------------------------------- #
# Inbound auth — validating incoming requests
# --------------------------------------------------------------------------- #


DEFAULT_DEV_CLAIMS = TokenClaims(
    sub="dev|local-placeholder",
    email="dev@example.com",
    name="Dev User",
    permissions=ALL_PERMISSIONS,
    raw={},
)


def _dev_bearer_token() -> str:
    """Placeholder token used only when auth is disabled in local development."""
    return "dev-placeholder-token"


def _extract_bearer_token_from_request(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _default_user_from_claims(claims: TokenClaims) -> ServiceUser:
    return ServiceUser(
        id=1,
        sub=claims.sub,
        email=claims.email or "unknown@example.com",
        name=claims.name or claims.email or claims.sub,
    )


def _permission_exception_handler(exc: InsufficientPermissionsError) -> NoReturn:
    raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=exc.detail)


class ServiceAuth:
    """Inbound auth wiring shared by Stitch services.

    Produces the FastAPI dependencies a service needs (``get_token_claims``,
    ``require_permissions``, ``get_current_user``, ``get_request_auth_context``
    and their ``Annotated`` aliases ``Claims``/``CurrentUser``/``AuthContext``).
    A service constructs one instance and re-exports the attributes it uses.

    Config seams:
      - ``is_auth_disabled``: callable read per request; when true, all requests
        resolve to ``dev_claims`` (local-dev bypass).
      - ``user_factory``: maps validated claims to a user (override to hit a DB).
      - ``oidc_settings_factory`` / ``dev_claims``: rarely overridden.
    """

    def __init__(
        self,
        *,
        is_auth_disabled: Callable[[], bool],
        oidc_settings_factory: Callable[[], OIDCSettings] = OIDCSettings,
        dev_claims: TokenClaims | None = None,
        user_factory: Callable[[TokenClaims], ServiceUser] = _default_user_from_claims,
    ) -> None:
        self._is_auth_disabled = is_auth_disabled
        self._oidc_settings_factory = oidc_settings_factory
        self._dev_claims = dev_claims if dev_claims is not None else DEFAULT_DEV_CLAIMS
        self._user_factory = user_factory
        self._oidc_settings: OIDCSettings | None = None
        self._validator: JWTValidator | None = None

        # auto_error=False so a missing header doesn't 403 before our handler
        # runs (and so AUTH_DISABLED can short-circuit).
        bearer_scheme = HTTPBearer(auto_error=False)

        async def get_token_claims(
            request: Request,
            _credential: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        ) -> TokenClaims:
            """Extract and validate the JWT from the Authorization header.

            ``_credential`` exists only so FastAPI registers the HTTPBearer
            scheme in OpenAPI (the Swagger "Authorize" button); token parsing
            uses the raw header for precise 401 messages.
            """
            if self._is_auth_disabled():
                return self._dev_claims

            auth_header = request.headers.get("Authorization")
            if not auth_header:
                raise HTTPException(
                    status_code=HTTP_401_UNAUTHORIZED,
                    detail="Missing Authorization header",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            scheme, _, token = auth_header.partition(" ")
            if scheme.lower() != "bearer" or not token:
                raise HTTPException(
                    status_code=HTTP_401_UNAUTHORIZED,
                    detail="Invalid Authorization header format",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            validator = self._jwt_validator()
            try:
                return await asyncio.to_thread(validator.validate, token)
            except JWKSFetchError:
                logger.error(
                    "JWKS endpoint unreachable or returned invalid data",
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            except AuthError as exc:
                logger.warning("JWT validation failed: %s", exc, exc_info=True)
                raise HTTPException(
                    status_code=HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        Claims = Annotated[TokenClaims, Depends(get_token_claims)]

        def require_permissions(
            *required_permissions: str, check: Literal["all", "any"] = "all"
        ):
            async def dependency(claims: Claims) -> None:
                check_permissions(
                    granted=claims.permissions,
                    required=required_permissions,
                    check=check,
                    exc_handler=_permission_exception_handler,
                )

            return dependency

        async def get_current_user(claims: Claims) -> ServiceUser:
            # When auth is disabled, `claims` is already the dev claims.
            return self._user_factory(claims)

        CurrentUser = Annotated[ServiceUser, Depends(get_current_user)]

        async def get_request_auth_context(
            request: Request, user: CurrentUser
        ) -> RequestAuthContext:
            if self._is_auth_disabled():
                bearer_token = _dev_bearer_token()
            else:
                bearer_token = _extract_bearer_token_from_request(request)
            return RequestAuthContext(user=user, bearer_token=bearer_token)

        AuthContext = Annotated[RequestAuthContext, Depends(get_request_auth_context)]

        async def initiated_by(auth_context: AuthContext) -> str:
            """Caller label for attributing a job's ``initiated_by``."""
            return auth_context.user.label

        self.get_token_claims = get_token_claims
        self.require_permissions = require_permissions
        self.get_current_user = get_current_user
        self.get_request_auth_context = get_request_auth_context
        self.initiated_by = initiated_by
        self.Claims = Claims
        self.CurrentUser = CurrentUser
        self.AuthContext = AuthContext

    def oidc_settings(self) -> OIDCSettings:
        if self._oidc_settings is None:
            self._oidc_settings = self._oidc_settings_factory()
        return self._oidc_settings

    def _jwt_validator(self) -> JWTValidator:
        if self._validator is None:
            self._validator = JWTValidator(self.oidc_settings())
        return self._validator

    def validate_auth_config_at_startup(self) -> None:
        if self._is_auth_disabled():
            logger.warning("Auth is disabled — all requests use dev credentials")
            return
        # Fail fast if OIDC config is invalid.
        self.oidc_settings()
