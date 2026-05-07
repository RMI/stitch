"""Unit tests for auth module startup validation and token claims."""

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from stitch.api.auth import (
    get_current_user,
    get_token_claims,
    validate_auth_config_at_startup,
)
from stitch.api.entities import User
from stitch.api.main import app
from stitch.api.settings import Settings
from stitch.auth import TokenClaims
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


class TestAuthMeEndpoint:
    """Route tests for /auth/me."""

    def test_returns_resolved_user_and_claims(self):
        settings = _make_settings(auth_disabled=False)
        oidc_settings = _make_oidc_settings()
        claims = TokenClaims(
            sub="auth0|claims-user",
            email="claims@example.com",
            name="Claims User",
            permissions=frozenset(
                {"resource:read:licensed:wm", "resource:read:public"}
            ),
            raw={"permissions": ["resource:read:public", "resource:read:licensed:wm"]},
        )
        user = User(
            id=42,
            sub="auth0|claims-user",
            email="claims@example.com",
            name="Claims User",
        )

        def override_get_token_claims() -> TokenClaims:
            return claims

        def override_get_current_user() -> User:
            return user

        app.dependency_overrides[get_token_claims] = override_get_token_claims
        app.dependency_overrides[get_current_user] = override_get_current_user

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
                    "resource:read:licensed:wm",
                    "resource:read:public",
                ],
                "raw": {
                    "permissions": [
                        "resource:read:public",
                        "resource:read:licensed:wm",
                    ]
                },
            },
        }
