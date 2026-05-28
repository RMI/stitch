"""Unit tests for auth module startup validation and token claims."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.testclient import TestClient

from stitch.api.auth import (
    get_token_claims,
    require_permissions,
    validate_auth_config_at_startup,
)
from stitch.api.db.config import get_uow
from stitch.api.entities import User
from stitch.api.main import app
from stitch.api.settings import Settings
from stitch.auth import TokenClaims
from stitch.auth.permissions import RESOURCE_READ, RESOURCE_WRITE, SOURCE_READ_WM
from stitch.auth.settings import OIDCSettings


def _make_settings(
    *, auth_disabled: bool = False, environment: str = "dev"
) -> Settings:
    """Build a Settings instance with overridden fields."""
    return Settings(
        auth_disabled=auth_disabled,
        environment=environment,
    )


def _make_oidc_settings(
    *,
    issuer: str = "https://example.com",
    audience: str = "ex_aud",
    jwks_uri: str = "https://auth.example.com/jwks",
) -> OIDCSettings:
    return OIDCSettings(issuer=issuer, audience=audience, jwks_uri=jwks_uri)


class TestValidateAuthConfigAtStartup:
    """Unit tests for validate_auth_config_at_startup."""

    def test_allows_disabled_in_dev(self):
        """No error when auth_disabled=True in DEV environment."""
        settings = _make_settings(auth_disabled=True, environment="development")
        with patch("stitch.api.auth.get_settings", return_value=settings):
            validate_auth_config_at_startup()

    def test_allows_disabled_in_pr_environment_lowercase(self):
        settings = _make_settings(auth_disabled=True, environment="pr-123")
        with patch("stitch.api.auth.get_settings", return_value=settings):
            validate_auth_config_at_startup()

    def test_allows_disabled_in_pr_environment_uppercase(self):
        settings = _make_settings(auth_disabled=True, environment="PR-123")
        with patch("stitch.api.auth.get_settings", return_value=settings):
            validate_auth_config_at_startup()

    def test_allows_disabled_in_main(self):
        settings = _make_settings(auth_disabled=True, environment="main")
        with patch("stitch.api.auth.get_settings", return_value=settings):
            validate_auth_config_at_startup()

    def test_blocks_disabled_in_prod(self):
        """RuntimeError when auth_disabled=True in PROD environment."""
        settings = _make_settings(auth_disabled=True, environment="production")
        with patch("stitch.api.auth.get_settings", return_value=settings):
            with pytest.raises(
                RuntimeError,
                match="AUTH_DISABLED=true is only permitted when ENVIRONMENT is one of",
            ):
                validate_auth_config_at_startup()

    def test_blocks_disabled_in_test(self):
        """RuntimeError when auth_disabled=True in TEST environment."""
        settings = _make_settings(auth_disabled=True, environment="TEST")
        with patch("stitch.api.auth.get_settings", return_value=settings):
            with pytest.raises(
                RuntimeError,
                match="AUTH_DISABLED=true is only permitted when ENVIRONMENT is one of",
            ):
                validate_auth_config_at_startup()

    def test_validates_oidc_settings_when_enabled(self):
        """Calls get_oidc_settings() when auth is enabled to fail fast."""
        settings = _make_settings(auth_disabled=False)
        with (
            patch("stitch.api.auth.get_settings", return_value=settings),
            patch("stitch.api.auth.get_oidc_settings") as mock_oidc,
        ):
            validate_auth_config_at_startup()
            mock_oidc.assert_called_once()


class TestGetTokenClaims:
    """Unit tests for get_token_claims dependency."""

    def test_returns_dev_claims_when_disabled(self):
        """Returns _DEV_CLAIMS when auth is disabled."""
        settings = _make_settings(auth_disabled=True, environment="development")
        oidc_settings = _make_oidc_settings()

        with (
            patch("stitch.api.auth.get_settings", return_value=settings),
            patch("stitch.api.auth.get_oidc_settings", return_value=oidc_settings),
        ):
            with TestClient(app) as client:
                response = client.get("/api/v1/health")

            assert response.status_code == 200

    def test_raises_401_missing_auth_header(self):
        """401 when no Authorization header and auth is enabled."""
        settings = _make_settings(auth_disabled=False)
        oidc_settings = _make_oidc_settings()

        with (
            patch("stitch.api.auth.get_settings", return_value=settings),
            patch("stitch.api.auth.get_oidc_settings", return_value=oidc_settings),
        ):
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get(
                    "/api/v1/oil-gas-fields/",
                )

            assert response.status_code == 401
            assert response.json()["detail"] == "Missing Authorization header"

    def test_raises_401_invalid_header_format(self):
        """401 for malformed Authorization header."""
        settings = _make_settings(auth_disabled=False)
        oidc_settings = _make_oidc_settings()

        with (
            patch("stitch.api.auth.get_settings", return_value=settings),
            patch("stitch.api.auth.get_oidc_settings", return_value=oidc_settings),
        ):
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get(
                    "/api/v1/oil-gas-fields/",
                    headers={"Authorization": "NotBearer sometoken"},
                )

            assert response.status_code == 401
            assert response.json()["detail"] == "Invalid Authorization header format"


class TestRequirePermissions:
    """Unit tests for the API permission dependency wrapper."""

    @pytest.mark.anyio
    async def test_default_check_requires_all_permissions(self):
        dependency = require_permissions(RESOURCE_READ, RESOURCE_WRITE)
        claims = TokenClaims(
            sub="auth0|permission-user",
            permissions=frozenset({RESOURCE_READ, RESOURCE_WRITE}),
        )

        assert await dependency(claims) is None

    @pytest.mark.anyio
    async def test_default_check_raises_403_for_missing_permission(self):
        dependency = require_permissions(RESOURCE_READ, RESOURCE_WRITE)
        claims = TokenClaims(
            sub="auth0|permission-user",
            permissions=frozenset({RESOURCE_READ}),
        )

        with pytest.raises(HTTPException) as exc_info:
            await dependency(claims)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == (
            "Missing required permission(s): resource:write"
        )

    @pytest.mark.anyio
    async def test_any_check_accepts_one_candidate_permission(self):
        dependency = require_permissions(
            RESOURCE_WRITE,
            SOURCE_READ_WM,
            check="any",
        )
        claims = TokenClaims(
            sub="auth0|permission-user",
            permissions=frozenset({SOURCE_READ_WM}),
        )

        assert await dependency(claims) is None

    @pytest.mark.anyio
    async def test_any_check_raises_403_when_no_candidates_match(self):
        dependency = require_permissions(
            RESOURCE_WRITE,
            SOURCE_READ_WM,
            check="any",
        )
        claims = TokenClaims(
            sub="auth0|permission-user",
            permissions=frozenset({RESOURCE_READ}),
        )

        with pytest.raises(HTTPException) as exc_info:
            await dependency(claims)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == (
            "Missing required permission(s): resource:write, source:read:wm"
        )


class TestAuthMeEndpoint:
    """Route tests for /auth/me."""

    def test_returns_existing_user_and_claims(self):
        settings = _make_settings(auth_disabled=False)
        oidc_settings = _make_oidc_settings()
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

        def override_get_token_claims() -> TokenClaims:
            return claims

        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        uow = MagicMock()
        uow.session = session

        async def override_get_uow():
            yield uow

        app.dependency_overrides[get_token_claims] = override_get_token_claims
        app.dependency_overrides[get_uow] = override_get_uow

        with (
            patch("stitch.api.auth.get_settings", return_value=settings),
            patch("stitch.api.auth.get_oidc_settings", return_value=oidc_settings),
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
        oidc_settings = _make_oidc_settings()
        claims = TokenClaims(
            sub="auth0|claims-only",
            email=None,
            name=None,
            permissions=frozenset({RESOURCE_READ}),
            raw={"permissions": [RESOURCE_READ]},
        )

        def override_get_token_claims() -> TokenClaims:
            return claims

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        uow = MagicMock()
        uow.session = session

        async def override_get_uow():
            yield uow

        app.dependency_overrides[get_token_claims] = override_get_token_claims
        app.dependency_overrides[get_uow] = override_get_uow

        with (
            patch("stitch.api.auth.get_settings", return_value=settings),
            patch("stitch.api.auth.get_oidc_settings", return_value=oidc_settings),
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
