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


def _as_list(scopes: str | list[str] | None) -> list[str]:
    if scopes is None:
        return []
    return [scopes] if isinstance(scopes, str) else list(scopes)


def check_scopes(granted: frozenset[str], required: Iterable[str]) -> None:
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
    def require_auth(
        self, scopes: str | list[str] | None = None
    ) -> Callable[[Request], Awaitable[TokenClaims]]:
        verify = super().require_auth()
        required = _as_list(scopes)

        async def dependency(request: Request) -> TokenClaims:
            raw: dict[str, Any] = await verify(request)
            permissions = frozenset(raw.get("permissions", []))
            claims = TokenClaims(
                sub=raw["sub"],
                email=raw.get("email", raw.get("preferred_username")),
                name=raw.get("name"),
                permissions=permissions,
                raw=raw,
            )
            check_scopes(claims.permissions, required)
            return claims

        return dependency


class StaticAuthProvider:
    def __init__(self, claims: TokenClaims) -> None:
        self._claims = claims

    def require_auth(
        self, scopes: str | list[str] | None = None
    ) -> Callable[[Request], Awaitable[TokenClaims]]:
        required = _as_list(scopes)

        async def dependency(request: Request) -> TokenClaims:
            check_scopes(self._claims.permissions, required)
            return self._claims

        return dependency


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
    *scopes: str,
) -> Callable[[Request, AuthProvider], Awaitable[TokenClaims]]:
    async def dependency(request: Request, provider: AuthProviderDep) -> TokenClaims:
        return await provider.require_auth(list(scopes))(request)

    return dependency


def require_user(
    *scopes: str,
) -> Callable[..., Awaitable[AuthenticatedUser]]:
    async def dependency(
        claims: Annotated[TokenClaims, Depends(require_auth(*scopes))],
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
