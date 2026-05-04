import asyncio
import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.status import HTTP_401_UNAUTHORIZED

from stitch.auth import JWTValidator, OIDCSettings, TokenClaims
from stitch.auth.errors import AuthError, JWKSFetchError

from stitch.llm.entities import User
from stitch.llm.settings import get_settings

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
    raw={},
)

# auto_error=False so that when AUTH_DISABLED=true the missing header
# doesn't trigger a 403 before our custom handler runs.
_bearer_scheme = HTTPBearer(auto_error=False)


def validate_auth_config_at_startup() -> None:
    settings = get_settings()

    if settings.auth_disabled:
        logger.warning("Auth is disabled — all requests use dev credentials")
        return

    # fail fast if OIDC config is invalid
    get_oidc_settings()


def _claims_to_user(claims: TokenClaims) -> User:
    return User(
        id=1,
        sub=claims.sub,
        email=claims.email or "unknown@example.com",
        name=claims.name or claims.email or claims.sub,
    )


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

    validator = get_jwt_validator()
    try:
        return await asyncio.to_thread(validator.validate, token)
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


Claims = Annotated[TokenClaims, Depends(get_token_claims)]


async def get_current_user(claims: Claims) -> User:
    """
    Resolve validated token claims to a lightweight request user.
    """
    if get_settings().auth_disabled:
        return User(
            id=1,
            sub=_DEV_CLAIMS.sub,
            email=_DEV_CLAIMS.email or "dev@example.com",
            name=_DEV_CLAIMS.name or "Dev User",
        )
    return _claims_to_user(claims)


CurrentUser = Annotated[User, Depends(get_current_user)]
