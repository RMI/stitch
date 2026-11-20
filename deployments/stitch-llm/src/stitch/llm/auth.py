import logging
from functools import lru_cache
from typing import Annotated, Any, ClassVar

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi_plugin import Auth0FastAPI
from pydantic import BaseModel, Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from stitch.llm.entities import User
from stitch.llm.settings import get_settings

logger = logging.getLogger(__name__)

SERVICE_LLM_SUGGEST = "service:llm:suggest"


class TokenClaims(BaseModel):
    sub: str
    email: str | None = None
    name: str | None = None
    permissions: frozenset[str] = Field(default_factory=frozenset)
    raw: dict[str, Any] = Field(default_factory=dict)


class AuthSettings(BaseSettings):
    issuer: HttpUrl
    audience: str

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="AUTH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_auth0() -> Auth0FastAPI:
    auth_settings = AuthSettings()
    return Auth0FastAPI(
        domain=auth_settings.issuer.host, audience=auth_settings.audience
    )


_DEV_CLAIMS = TokenClaims(
    sub="dev|local-placeholder",
    email="dev@example.com",
    name="Dev User",
    permissions=frozenset({SERVICE_LLM_SUGGEST}),
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
    get_auth0()


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

    raw = await get_auth0().require_auth()(request)
    return TokenClaims(
        sub=raw["sub"],
        name=raw.get("name"),
        permissions=frozenset(raw.get("permissions") or []),
        raw=raw,
    )


Claims = Annotated[TokenClaims, Depends(get_token_claims)]


def require_permissions(*required_permissions: str):
    async def dependency(claims: Claims) -> None:
        missing = sorted(set(required_permissions) - claims.permissions)
        if missing:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail=f"Missing required permission(s): {', '.join(missing)}",
            )

    return dependency


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
