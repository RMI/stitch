import logging
from collections.abc import Awaitable, Callable, Iterable
from fnmatch import fnmatchcase
from functools import lru_cache
from typing import Annotated, Any, ClassVar

from fastapi import Depends, HTTPException, Request
from fastapi_plugin import Auth0FastAPI
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from starlette.status import HTTP_403_FORBIDDEN

from stitch.api.db.config import SessionFactoryDep
from stitch.api.db.model.user import User as UserModel
from stitch.api.settings import get_settings

from .permissions import ALL_PERMISSIONS
from .typings import AuthenticatedUser, AuthProvider, TokenClaims

logger = logging.getLogger(__name__)


class AuthSettings(BaseSettings):
    domain: str
    audience: str
    client_id: str | None = None
    client_secret: str | None = None

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="STITCH_AUTH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings()


def check_permissions(granted: frozenset[str], required: Iterable[str]) -> None:
    missing = sorted(
        pattern
        for pattern in required
        if not any(fnmatchcase(permission, pattern) for permission in granted)
    )
    if missing:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=f"Missing required permission(s): {', '.join(missing)}",
        )


class Auth0AuthProvider(Auth0FastAPI):
    async def authenticate(self, request: Request) -> TokenClaims:
        raw: dict[str, Any] = await self.require_auth()(request)
        return TokenClaims(
            sub=raw["sub"],
            email=raw.get("email", raw.get("preferred_username")),
            name=raw.get("name"),
            permissions=frozenset(raw.get("permissions", [])),
            raw=raw,
        )


class StaticAuthProvider:
    def __init__(self, claims: TokenClaims) -> None:
        self._claims = claims

    async def authenticate(self, request: Request) -> TokenClaims:
        return self._claims


DEV_CLAIMS = TokenClaims(
    sub="dev|local-placeholder",
    email="dev@example.com",
    name="Dev User",
    permissions=ALL_PERMISSIONS,
)


@lru_cache
def get_auth_provider() -> AuthProvider:
    settings = get_settings()
    if settings.auth_disabled:
        if not settings.allows_disabled_auth:
            raise RuntimeError(
                "AUTH_DISABLED=true is only permitted in dev, main, dev-* or pr-* environments."
            )
        logger.warning("Auth is disabled; all requests use dev credentials")
        return StaticAuthProvider(DEV_CLAIMS)
    auth_settings = get_auth_settings()
    return Auth0AuthProvider(**auth_settings.model_dump())


AuthProviderDep = Annotated[AuthProvider, Depends(get_auth_provider)]


def require_auth(
    *permissions: str,
) -> Callable[[Request, AuthProvider], Awaitable[TokenClaims]]:
    async def dependency(request: Request, provider: AuthProviderDep) -> TokenClaims:
        claims = await provider.authenticate(request)
        check_permissions(claims.permissions, permissions)
        return claims

    return dependency


def require_user(
    *permissions: str,
) -> Callable[..., Awaitable[AuthenticatedUser]]:
    async def dependency(
        claims: Annotated[TokenClaims, Depends(require_auth(*permissions))],
        session_factory: SessionFactoryDep,
    ) -> AuthenticatedUser:
        return await _provision_user(claims, session_factory)

    return dependency


async def _provision_user(
    claims: TokenClaims, session_factory: SessionFactoryDep
) -> AuthenticatedUser:
    name = _normalized(claims.name)
    email = _normalized(claims.email)
    async with session_factory() as session:
        user_model = (
            await session.execute(select(UserModel).where(UserModel.sub == claims.sub))
        ).scalar_one_or_none()
        if user_model is None:
            user_model = UserModel(sub=claims.sub, name=name, email=email)
            session.add(user_model)
        else:
            if name is not None:
                user_model.name = name
            if email is not None:
                user_model.email = email
        await session.commit()
        return AuthenticatedUser(
            id=user_model.id,
            sub=user_model.sub,
            email=user_model.email,
            name=user_model.name,
            claims=claims,
        )


def _normalized(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None
