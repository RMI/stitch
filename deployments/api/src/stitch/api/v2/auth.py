import functools
from functools import lru_cache, Placeholder
from stitch.auth import TokenClaims
from fastapi_plugin import Auth0FastAPI
from pydantic_settings import BaseSettings, SettingsConfigDict
from types import CoroutineType
from fastapi import Request, Depends
from collections.abc import Callable
from typing import Protocol, Any, Annotated, ClassVar


class AuthProvider(Protocol):
    def require_auth(
        self, scopes: str | list[str] | None = None
    ) -> Callable[[Request], CoroutineType[Any, Any, TokenClaims]]: ...


class AuthSettings(BaseSettings):
    domain: str
    audience: str
    client_id: str | None
    client_secret: str | None

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings()


def _configure_provider[T: AuthProvider, **P](
    provider_klass: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> T:
    return provider_klass(*args, **kwargs)


def _conf[T: AuthProvider, **P]() -> Callable[[Callable[P, T]], T]:
    kw = get_auth_settings().model_dump()
    return functools.partial(_configure_provider, Placeholder, **kw)


def configure_provider[T: AuthProvider](
    prov_kls: type[T],
) -> Callable[..., AuthProvider]:
    auth_settings = get_auth_settings()

    return lambda: prov_kls(**auth_settings.model_dump())


def provide_auth[T: AuthProvider, **P](provider_klass: Callable[P, T]):

    def _configure(*args: P.args, **kwargs: P.kwargs) -> T:
        return provider_klass(*args, **kwargs)

    return _configure


class OilGasAuthProviderAuth0(Auth0FastAPI):
    def require_auth(
        self, scopes: str | list[str] | None = None
    ) -> Callable[[Request], CoroutineType[Any, Any, TokenClaims]]:
        sup_ = super()

        async def dep(request: Request):
            claims: dict[str, Any] = await sup_.require_auth(scopes=scopes)(request)
            email = claims.get("email", claims.get("preferred_username"))
            name = claims.get("name")
            _claim_perm: list[str] = claims.get("permissions", [])
            _claim_scope: list[str] = claims.get("scope", "").split()
            permissions: frozenset[str] = frozenset(_claim_perm + _claim_scope)

            return TokenClaims(
                sub=claims["sub"],
                name=name,
                email=email,
                permissions=permissions,
                raw=claims,
            )

        return dep


AuthProviderDep = Annotated[
    AuthProvider, Depends(configure_provider(OilGasAuthProviderAuth0))
]


def require_permissions(*perms: str):
    prov = configure_provider(OilGasAuthProviderAuth0)()
    return prov.require_auth(scopes=list(perms))
