"""Unit tests for auth provider startup selection, permission checks, and /auth/me."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.testclient import TestClient

from stitch.api._auth import (
    RESOURCE_READ,
    RESOURCE_WRITE,
    SOURCE_READ_PREFIX,
    AuthProvider,
    StaticAuthProvider,
    TokenClaims,
    get_auth_provider,
)
from stitch.api._auth.impl import Auth0AuthProvider, AuthSettings, check_scopes
from stitch.api.db.config import get_uow
from stitch.api.entities import User
from stitch.api.main import app
from stitch.api.settings import Settings

SOURCE_READ_WM = f"{SOURCE_READ_PREFIX}wm"


def _make_settings(
    *, auth_disabled: bool = False, environment: str = "dev"
) -> Settings:
    """Build a Settings instance with overridden fields."""
    return Settings(
        auth_disabled=auth_disabled,
        environment=environment,
    )


def _make_auth_settings() -> AuthSettings:
    return AuthSettings(domain="example.us.auth0.com", audience="ex_aud")


def _build_provider(settings: Settings) -> AuthProvider:
    get_auth_provider.cache_clear()
    with patch("stitch.api._auth.impl.get_settings", return_value=settings):
        return get_auth_provider()


class TestGetAuthProvider:
    """Unit tests for get_auth_provider, which also runs at startup."""

    def test_allows_disabled_in_dev(self):
        """No error when auth_disabled=True in DEV environment."""
        settings = _make_settings(auth_disabled=True, environment="development")
        assert isinstance(_build_provider(settings), StaticAuthProvider)

    def test_allows_disabled_in_pr_environment_lowercase(self):
        settings = _make_settings(auth_disabled=True, environment="pr-123")
        assert isinstance(_build_provider(settings), StaticAuthProvider)

    def test_allows_disabled_in_pr_environment_uppercase(self):
        settings = _make_settings(auth_disabled=True, environment="PR-123")
        assert isinstance(_build_provider(settings), StaticAuthProvider)

    def test_allows_disabled_in_main(self):
        settings = _make_settings(auth_disabled=True, environment="main")
        assert isinstance(_build_provider(settings), StaticAuthProvider)

    def test_blocks_disabled_in_prod(self):
        """RuntimeError when auth_disabled=True in PROD environment."""
        settings = _make_settings(auth_disabled=True, environment="production")
        with pytest.raises(RuntimeError, match="AUTH_DISABLED=true is only permitted"):
            _build_provider(settings)

    def test_blocks_disabled_in_test(self):
        """RuntimeError when auth_disabled=True in TEST environment."""
        settings = _make_settings(auth_disabled=True, environment="TEST")
        with pytest.raises(RuntimeError, match="AUTH_DISABLED=true is only permitted"):
            _build_provider(settings)

    def test_reads_auth_settings_when_enabled(self):
        """Reads the Auth0 settings when auth is enabled, to fail fast."""
        settings = _make_settings(auth_disabled=False)
        with patch(
            "stitch.api._auth.impl.get_auth_settings",
            return_value=_make_auth_settings(),
        ) as mock_auth_settings:
            provider = _build_provider(settings)
        mock_auth_settings.assert_called_once()
        assert isinstance(provider, Auth0AuthProvider)

    def test_app_starts_when_disabled(self):
        """The app starts and serves requests when auth is disabled."""
        settings = _make_settings(auth_disabled=True, environment="development")

        with patch("stitch.api._auth.impl.get_settings", return_value=settings):
            with TestClient(app) as client:
                response = client.get("/api/v1/health")

        assert response.status_code == 200


class TestCheckScopes:
    """Unit tests for the permission check used by every provider."""

    def test_passes_when_all_permissions_granted(self):
        assert (
            check_scopes(
                frozenset({RESOURCE_READ, RESOURCE_WRITE}),
                [RESOURCE_READ, RESOURCE_WRITE],
            )
            is None
        )

    def test_raises_403_for_missing_permission(self):
        with pytest.raises(HTTPException) as exc_info:
            check_scopes(frozenset({RESOURCE_READ}), [RESOURCE_READ, RESOURCE_WRITE])

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == (
            "Missing required permission(s): resource:write"
        )


class TestAuthMeEndpoint:
    """Route tests for /auth/me."""

    def test_returns_existing_user_and_claims(self):
        settings = _make_settings(auth_disabled=False)
        claims = TokenClaims(
            sub="auth0|claims-user",
            email="claims@example.com",
            name="Claims User",
            permissions=frozenset({RESOURCE_READ, SOURCE_READ_WM}),
            raw={"permissions": [RESOURCE_READ, SOURCE_READ_WM]},
        )
        user = User(
            id=42,
            sub="auth0|claims-user",
            email="claims@example.com",
            name="Claims User",
        )

        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        uow = MagicMock()
        uow.session = session

        async def override_get_uow():
            yield uow

        app.dependency_overrides[get_auth_provider] = lambda: StaticAuthProvider(claims)
        app.dependency_overrides[get_uow] = override_get_uow

        with (
            patch("stitch.api._auth.impl.get_settings", return_value=settings),
            patch(
                "stitch.api._auth.impl.get_auth_settings",
                return_value=_make_auth_settings(),
            ),
        ):
            with TestClient(app) as client:
                response = client.get("/api/v1/auth/me")

        assert response.status_code == 200
        assert response.json() == {
            "user": {
                "id": 42,
                "sub": "auth0|claims-user",
                "role": None,
                "email": "claims@example.com",
                "name": "Claims User",
            },
            "claims": {
                "sub": "auth0|claims-user",
                "email": "claims@example.com",
                "name": "Claims User",
                "permissions": [
                    "resource:read",
                    "source:read:wm",
                ],
                "raw": {
                    "permissions": [
                        "resource:read",
                        "source:read:wm",
                    ]
                },
            },
        }

    def test_returns_claims_when_user_not_in_table(self):
        settings = _make_settings(auth_disabled=False)
        claims = TokenClaims(
            sub="auth0|claims-only",
            email=None,
            name=None,
            permissions=frozenset({RESOURCE_READ}),
            raw={"permissions": [RESOURCE_READ]},
        )

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        uow = MagicMock()
        uow.session = session

        async def override_get_uow():
            yield uow

        app.dependency_overrides[get_auth_provider] = lambda: StaticAuthProvider(claims)
        app.dependency_overrides[get_uow] = override_get_uow

        with (
            patch("stitch.api._auth.impl.get_settings", return_value=settings),
            patch(
                "stitch.api._auth.impl.get_auth_settings",
                return_value=_make_auth_settings(),
            ),
        ):
            with TestClient(app) as client:
                response = client.get("/api/v1/auth/me")

        assert response.status_code == 200
        assert response.json() == {
            "user": None,
            "claims": {
                "sub": "auth0|claims-only",
                "email": None,
                "name": None,
                "permissions": ["resource:read"],
                "raw": {"permissions": ["resource:read"]},
            },
        }
