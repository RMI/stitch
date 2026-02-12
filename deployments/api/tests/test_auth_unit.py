"""Unit tests for auth module startup validation and token claims."""

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from stitch.api.auth import validate_auth_config_at_startup
from stitch.api.main import app
from stitch.api.settings import Environment, Settings


def _make_settings(
    *, auth_disabled: bool = False, environment: Environment = Environment.DEV
) -> Settings:
    """Build a Settings instance with overridden fields."""
    return Settings(
        auth_disabled=auth_disabled,
        environment=environment,
    )


class TestValidateAuthConfigAtStartup:
    """Unit tests for validate_auth_config_at_startup."""

    def test_allows_disabled_in_dev(self):
        """No error when auth_disabled=True in DEV environment."""
        settings = _make_settings(auth_disabled=True, environment=Environment.DEV)
        with patch("stitch.api.auth.get_settings", return_value=settings):
            validate_auth_config_at_startup()

    def test_blocks_disabled_in_prod(self):
        """RuntimeError when auth_disabled=True in PROD environment."""
        settings = _make_settings(auth_disabled=True, environment=Environment.PROD)
        with patch("stitch.api.auth.get_settings", return_value=settings):
            with pytest.raises(
                RuntimeError, match="only permitted when ENVIRONMENT=dev"
            ):
                validate_auth_config_at_startup()

    def test_blocks_disabled_in_test(self):
        """RuntimeError when auth_disabled=True in TEST environment."""
        settings = _make_settings(auth_disabled=True, environment=Environment.TEST)
        with patch("stitch.api.auth.get_settings", return_value=settings):
            with pytest.raises(
                RuntimeError, match="only permitted when ENVIRONMENT=dev"
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
        settings = _make_settings(auth_disabled=True, environment=Environment.DEV)

        with (
            patch("stitch.api.auth.get_settings", return_value=settings),
            patch(
                "stitch.api.auth.validate_auth_config_at_startup",
            ),
        ):
            with TestClient(app) as client:
                response = client.get("/api/v1/health")

            assert response.status_code == 200

    def test_raises_401_missing_auth_header(self):
        """401 when no Authorization header and auth is enabled."""
        settings = _make_settings(auth_disabled=False)

        with (
            patch("stitch.api.auth.get_settings", return_value=settings),
            patch(
                "stitch.api.auth.validate_auth_config_at_startup",
            ),
        ):
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get(
                    "/api/v1/resources",
                )

            assert response.status_code == 401
            assert response.json()["detail"] == "Missing Authorization header"

    def test_raises_401_invalid_header_format(self):
        """401 for malformed Authorization header."""
        settings = _make_settings(auth_disabled=False)

        with (
            patch("stitch.api.auth.get_settings", return_value=settings),
            patch(
                "stitch.api.auth.validate_auth_config_at_startup",
            ),
        ):
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get(
                    "/api/v1/resources",
                    headers={"Authorization": "NotBearer sometoken"},
                )

            assert response.status_code == 401
            assert response.json()["detail"] == "Invalid Authorization header format"
