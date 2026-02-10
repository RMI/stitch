"""Tests for TokenClaims construction edge cases."""

import pytest

from pydantic import ValidationError
from stitch.auth.claims import TokenClaims


class TestTokenClaimsConstruction:
    """TokenClaims model validation."""

    def test_minimal_claims(self):
        """Only sub is required."""
        claims = TokenClaims(sub="auth0|abc123")

        assert claims.sub == "auth0|abc123"
        assert claims.email is None
        assert claims.name is None
        assert claims.raw == {}

    def test_full_claims(self):
        """All fields populated."""
        claims = TokenClaims(
            sub="auth0|abc123",
            email="user@example.com",
            name="Jane Doe",
            raw={"custom": "value"},
        )

        assert claims.sub == "auth0|abc123"
        assert claims.email == "user@example.com"
        assert claims.name == "Jane Doe"
        assert claims.raw["custom"] == "value"

    def test_sub_is_required(self):
        """Missing sub raises ValidationError."""
        with pytest.raises(ValidationError):
            TokenClaims()  # pyright: ignore[reportCallIssue]

    def test_raw_defaults_to_empty_dict(self):
        """raw field defaults to empty dict, not shared reference."""
        claims1 = TokenClaims(sub="user1")
        claims2 = TokenClaims(sub="user2")

        claims1.raw["key"] = "value"

        assert "key" not in claims2.raw

    def test_uuid_sub(self):
        """Entra ID-style UUID sub."""
        claims = TokenClaims(sub="550e8400-e29b-41d4-a716-446655440000")
        assert claims.sub == "550e8400-e29b-41d4-a716-446655440000"

    def test_pipe_sub(self):
        """Auth0-style sub with pipe separator."""
        claims = TokenClaims(sub="auth0|abc123")
        assert claims.sub == "auth0|abc123"
