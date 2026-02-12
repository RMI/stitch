import asyncio
import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.status import HTTP_401_UNAUTHORIZED

from stitch.auth import JWTValidator, OIDCSettings, TokenClaims
from stitch.auth.errors import AuthError, JWKSFetchError

from stitch.api.db.config import UnitOfWorkDep
from stitch.api.db.model.user import User as UserModel
from stitch.api.entities import User
from stitch.api.settings import Environment, get_settings

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
    """Called from FastAPI lifespan. Fail fast if misconfigured."""
    settings = get_oidc_settings()
    if settings.disabled and get_settings().environment == Environment.PROD:
        raise RuntimeError(
            "AUTH_DISABLED=true is forbidden when ENVIRONMENT=prod. "
            "Remove AUTH_DISABLED or set it to false."
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
    settings = get_oidc_settings()

    if settings.disabled:
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


async def get_current_user(claims: Claims, uow: UnitOfWorkDep) -> User:
    """Resolve TokenClaims to a User entity. JIT provision on first login.

    Race-safe: uses a savepoint so concurrent first-login requests
    don't corrupt the outer transaction on IntegrityError.
    """
    session = uow.session

    user_model = (
        await session.execute(select(UserModel).where(UserModel.sub == claims.sub))
    ).scalar_one_or_none()

    if user_model is not None:
        user_model.name = claims.name or user_model.name
        user_model.email = claims.email or user_model.email
        return _to_entity(user_model)

    try:
        async with session.begin_nested():
            user_model = UserModel(
                sub=claims.sub,
                name=claims.name or "",
                email=claims.email or "",
            )
            session.add(user_model)
    except IntegrityError:
        user_model = (
            await session.execute(select(UserModel).where(UserModel.sub == claims.sub))
        ).scalar_one()

    return _to_entity(user_model)


def _to_entity(model: UserModel) -> User:
    return User(
        id=model.id,
        sub=model.sub,
        email=model.email,
        name=model.name,
    )


CurrentUser = Annotated[User, Depends(get_current_user)]
