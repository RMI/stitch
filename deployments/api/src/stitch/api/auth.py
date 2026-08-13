import asyncio
import hashlib
import logging
from collections import OrderedDict
from functools import lru_cache
from time import time
from typing import Annotated, Literal, NoReturn

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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

from stitch.api.db.config import SessionFactoryDep
from stitch.api.db.model.user import User as UserModel
from stitch.api.entities import User
from stitch.api.settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_oidc_settings() -> OIDCSettings:
    return OIDCSettings()


@lru_cache
def get_jwt_validator() -> JWTValidator:
    return JWTValidator(get_oidc_settings())


_DEV_CLAIMS = TokenClaims(
    sub="dev|local-placeholder",
    email="dev@example.com",
    name="Dev User",
    permissions=ALL_PERMISSIONS,
    raw={},
)

# auto_error=False so that when AUTH_DISABLED=true the missing header
# doesn't trigger a 403 before our custom handler runs.
_bearer_scheme = HTTPBearer(auto_error=False)


# Validated-claims cache.
#
# Validating a bearer token means an RSA signature verify, which costs real CPU on
# every single request. Callers reuse one token for a long time -- a browser tab
# for the life of its session, entity-linkage for an entire bulk run -- so the same
# token gets verified thousands of times to produce an identical answer.
#
# Three properties this must keep:
#
# * **Keyed on a digest, not the token.** This dict outlives the request, and there
#   is no reason to retain raw bearer tokens in a long-lived structure.
# * **Never extends a token's life.** Each entry carries the token's own ``exp``
#   and is dropped once reached, so a cache hit cannot resurrect an expired token.
# * **Only successful validations are cached.** Failures must keep hitting the
#   validator, or a token that failed transiently (e.g. JWKS fetch) would be stuck.
#
# Cached ``TokenClaims`` instances are shared between requests. That is safe only
# because nothing mutates them -- keep it that way, or hand out copies here.
#
# Security note, so it does not have to be re-derived on review: this does not
# weaken the auth model. A cache hit cannot outlive the token's own ``exp``, and
# revocation was never honoured mid-token anyway -- the API does no introspection,
# and permissions travel *inside* the token, so they cannot change without a new
# token being issued (which is a different digest, hence a different entry). The
# only thing traded away is that a *newly issued* token for the same subject does
# not invalidate the old one early, which was already true.
_CLAIMS_CACHE_MAX_ENTRIES = 1024
# Retire entries slightly before the token itself lapses, so anything close to
# expiry goes back through the real validator (which applies the configured clock
# skew) instead of being served from cache in its final moments.
_CLAIMS_CACHE_EXPIRY_MARGIN_S = 30.0

_claims_cache: OrderedDict[str, tuple[float, TokenClaims]] = OrderedDict()


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cached_claims(digest: str, now: float) -> TokenClaims | None:
    entry = _claims_cache.get(digest)
    if entry is None:
        return None
    expires_at, claims = entry
    if now >= expires_at:
        del _claims_cache[digest]
        return None
    _claims_cache.move_to_end(digest)
    return claims


def _cache_claims(digest: str, claims: TokenClaims, now: float) -> None:
    exp = claims.raw.get("exp")
    if not isinstance(exp, (int, float)) or isinstance(exp, bool):
        # The validator requires ``exp``, so this should be unreachable — but with
        # no trustworthy expiry there is no safe way to cache.
        return

    expires_at = float(exp) - _CLAIMS_CACHE_EXPIRY_MARGIN_S
    if expires_at <= now:
        return

    _claims_cache[digest] = (expires_at, claims)
    _claims_cache.move_to_end(digest)
    # Bounded so a flood of distinct tokens cannot grow this without limit;
    # least-recently-used entries go first.
    while len(_claims_cache) > _CLAIMS_CACHE_MAX_ENTRIES:
        _claims_cache.popitem(last=False)


def reset_claims_cache() -> None:
    """Drop every cached entry. Test-only; not part of the request flow."""
    _claims_cache.clear()


def validate_auth_config_at_startup() -> None:
    """Called from FastAPI lifespan. Fail fast if misconfigured."""
    settings = get_settings()
    if settings.auth_disabled:
        if not settings.allows_disabled_auth:
            raise RuntimeError(
                "AUTH_DISABLED=true is only permitted when ENVIRONMENT is one of dev, development, main, or starts with dev-* or pr-*."
            )
        logger.warning("Auth is disabled — all requests use dev credentials")
        return
    get_oidc_settings()  # fail fast if required OIDC fields missing


async def get_token_claims(
    request: Request,
    _credential: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> TokenClaims:
    """Extract and validate JWT from Authorization header.

    The ``_credential`` parameter exists solely so FastAPI registers the
    HTTPBearer security scheme in the OpenAPI spec (Swagger "Authorize"
    button).  Actual token parsing still uses the raw header so we can
    return precise 401 messages for missing/malformed values.
    """
    if get_settings().auth_disabled:
        return _DEV_CLAIMS

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

    digest = _token_digest(token)
    now = time()
    cached = _cached_claims(digest, now)
    if cached is not None:
        return cached

    validator = get_jwt_validator()
    try:
        claims = await asyncio.to_thread(validator.validate, token)
    except JWKSFetchError:
        logger.error(
            "JWKS endpoint unreachable or returned invalid data", exc_info=True
        )
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except AuthError as e:
        logger.warning("JWT validation failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not claims.permissions:
        # Emitted on validation, so once per token rather than once per request —
        # the condition is a property of the token, so repeating it adds nothing.
        logger.warning(
            "authenticated token has no permissions; protected routes will reject it"
        )
    _cache_claims(digest, claims, now)
    return claims


Claims = Annotated[TokenClaims, Depends(get_token_claims)]


def _permission_exception_handler(exc: InsufficientPermissionsError) -> NoReturn:
    raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=exc.detail)


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


async def get_current_user(claims: Claims, session_factory: SessionFactoryDep) -> User:
    """Resolve TokenClaims to a User entity. JIT provision on first login.

    Runs in a dedicated session so user creation and claim back-fill
    persist even if the request handler later errors.
    """
    async with session_factory() as session:
        try:
            user_model = (
                await session.execute(
                    select(UserModel).where(UserModel.sub == claims.sub)
                )
            ).scalar_one_or_none()

            if user_model is not None:
                _apply_claim_backfill(user_model, claims)
            else:
                user_model = UserModel(
                    sub=claims.sub,
                    name=_normalized_optional_claim_value(claims.name),
                    email=_normalized_optional_claim_value(claims.email),
                )
                session.add(user_model)

            await session.commit()
        except IntegrityError:
            await session.rollback()
            # Known risk: we do not try to recover from simultaneous first-login
            # races. If two requests create the same sub concurrently, one may
            # receive a transient 500 from the unique constraint violation.
            raise

        return _to_entity(user_model)


def _apply_claim_backfill(model: UserModel, claims: Claims) -> bool:
    updated = False
    normalized_name = _normalized_optional_claim_value(claims.name)
    normalized_email = _normalized_optional_claim_value(claims.email)

    if normalized_name is not None and normalized_name != model.name:
        model.name = normalized_name
        updated = True
    if normalized_email is not None and normalized_email != model.email:
        model.email = normalized_email
        updated = True
    return updated


def _normalized_optional_claim_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _to_entity(model: UserModel) -> User:
    return User(
        id=model.id,
        sub=model.sub,
        email=model.email,
        name=model.name,
    )


CurrentUser = Annotated[User, Depends(get_current_user)]
