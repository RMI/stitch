"""Tests for OIDCSettings parsing and validation."""

import pytest
from pydantic import ValidationError

from stitch.auth.settings import OIDCSettings


class TestOIDCSettingsValidation:
    """Validation rules for OIDCSettings."""

    def test_disabled_requires_no_other_fields(self):
        """AUTH_DISABLED=true should work without issuer/audience/jwks_uri."""
        settings = OIDCSettings(disabled=True)

        assert settings.disabled is True
        assert settings.issuer == ""
        assert settings.audience == ""
        assert settings.jwks_uri == ""

    def test_enabled_requires_issuer_audience_jwks_uri(self):
        """Missing required fields when auth is enabled raises ValidationError."""
        with pytest.raises(
            ValidationError, match="Required when AUTH_DISABLED is not true"
        ):
            OIDCSettings(disabled=False)

    def test_enabled_partial_fields_raises(self):
        """Providing only some required fields still raises."""
        with pytest.raises(
            ValidationError, match="Required when AUTH_DISABLED is not true"
        ):
            OIDCSettings(
                issuer="https://test.auth0.com/",
                audience="",
                jwks_uri="",
            )

    def test_enabled_all_fields_succeeds(self):
        """All required fields provided when enabled."""
        settings = OIDCSettings(
            issuer="https://test.auth0.com/",
            audience="https://api.example.com",
            jwks_uri="https://test.auth0.com/.well-known/jwks.json",
        )

        assert settings.issuer == "https://test.auth0.com/"
        assert settings.audience == "https://api.example.com"
        assert settings.disabled is False


class TestOIDCSettingsDefaults:
    """Default values for OIDCSettings."""

    def test_default_algorithms(self):
        settings = OIDCSettings(
            issuer="https://x.com/",
            audience="aud",
            jwks_uri="https://x.com/jwks",
        )
        assert settings.algorithms == ("RS256",)

    def test_default_cache_ttl(self):
        settings = OIDCSettings(
            issuer="https://x.com/",
            audience="aud",
            jwks_uri="https://x.com/jwks",
        )
        assert settings.jwks_cache_ttl == 600

    def test_default_clock_skew(self):
        settings = OIDCSettings(
            issuer="https://x.com/",
            audience="aud",
            jwks_uri="https://x.com/jwks",
        )
        assert settings.clock_skew_seconds == 30

    def test_default_disabled_is_false(self):
        """disabled defaults to False (auth is on by default)."""
        with pytest.raises(ValidationError):
            OIDCSettings()


class TestOIDCSettingsFromEnv:
    """Settings can be loaded from environment variables."""

    def test_from_env_vars(self, monkeypatch):
        monkeypatch.setenv("AUTH_ISSUER", "https://env.auth0.com/")
        monkeypatch.setenv("AUTH_AUDIENCE", "https://api.env.example.com")
        monkeypatch.setenv(
            "AUTH_JWKS_URI", "https://env.auth0.com/.well-known/jwks.json"
        )
        monkeypatch.setenv("AUTH_CLOCK_SKEW_SECONDS", "60")

        settings = OIDCSettings()

        assert settings.issuer == "https://env.auth0.com/"
        assert settings.audience == "https://api.env.example.com"
        assert settings.clock_skew_seconds == 60

    def test_disabled_from_env(self, monkeypatch):
        monkeypatch.setenv("AUTH_DISABLED", "true")

        settings = OIDCSettings()

        assert settings.disabled is True
