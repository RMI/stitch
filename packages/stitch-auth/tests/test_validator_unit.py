"""Unit tests for JWTValidator with mocked JWKS."""

import time

import jwt as pyjwt
import pytest

from stitch.auth.errors import JWKSFetchError, TokenExpiredError, TokenValidationError
from stitch.auth.validator import JWTValidator


class TestJWTValidatorHappyPath:
    """Successful token validation scenarios."""

    def test_validates_token_returns_claims(
        self, oidc_settings, mock_jwks_client, token_factory
    ):
        """Valid token produces TokenClaims with correct fields."""
        token = token_factory(
            sub="auth0|abc123",
            email="user@example.com",
            name="Jane Doe",
        )
        validator = JWTValidator(oidc_settings)

        claims = validator.validate(token)

        assert claims.sub == "auth0|abc123"
        assert claims.email == "user@example.com"
        assert claims.name == "Jane Doe"
        assert claims.raw["sub"] == "auth0|abc123"

    def test_email_fallback_to_preferred_username(
        self, oidc_settings, mock_jwks_client, token_factory
    ):
        """When email claim is absent, falls back to preferred_username."""
        token = token_factory(
            email=None,
            extra_claims={"preferred_username": "user@tenant.onmicrosoft.com"},
        )
        validator = JWTValidator(oidc_settings)

        claims = validator.validate(token)

        assert claims.email == "user@tenant.onmicrosoft.com"

    def test_optional_claims_can_be_absent(
        self, oidc_settings, mock_jwks_client, token_factory
    ):
        """email and name are optional."""
        token = token_factory(email=None, name=None)
        validator = JWTValidator(oidc_settings)

        claims = validator.validate(token)

        assert claims.email is None
        assert claims.name is None
        assert claims.sub == "auth0|user123"

    def test_raw_contains_full_payload(
        self, oidc_settings, mock_jwks_client, token_factory
    ):
        """raw dict contains the complete JWT payload."""
        token = token_factory(
            extra_claims={"given_name": "Jane", "family_name": "Doe"},
        )
        validator = JWTValidator(oidc_settings)

        claims = validator.validate(token)

        assert claims.raw["given_name"] == "Jane"
        assert claims.raw["family_name"] == "Doe"

    def test_uuid_sub_format(self, oidc_settings, mock_jwks_client, token_factory):
        """Entra ID-style UUID sub is treated as opaque string."""
        token = token_factory(sub="550e8400-e29b-41d4-a716-446655440000")
        validator = JWTValidator(oidc_settings)

        claims = validator.validate(token)

        assert claims.sub == "550e8400-e29b-41d4-a716-446655440000"

    def test_token_without_nbf_validates(
        self, oidc_settings, mock_jwks_client, token_factory
    ):
        """Token missing nbf claim (e.g. Auth0 default) validates successfully."""
        token = token_factory(include_nbf=False)
        validator = JWTValidator(oidc_settings)

        claims = validator.validate(token)

        assert claims.sub == "auth0|user123"


class TestJWTValidatorErrors:
    """Error handling and exception mapping."""

    def test_expired_token_raises_token_expired_error(
        self, oidc_settings, mock_jwks_client, token_factory
    ):
        """Expired token raises TokenExpiredError."""
        token = token_factory(exp=int(time.time()) - 3600)
        validator = JWTValidator(oidc_settings)

        with pytest.raises(TokenExpiredError):
            validator.validate(token)

    def test_wrong_audience_raises_token_validation_error(
        self, oidc_settings, mock_jwks_client, token_factory
    ):
        """Mismatched audience raises TokenValidationError."""
        token = token_factory(aud="https://wrong-audience.example.com")
        validator = JWTValidator(oidc_settings)

        with pytest.raises(TokenValidationError):
            validator.validate(token)

    def test_wrong_issuer_raises_token_validation_error(
        self, oidc_settings, mock_jwks_client, token_factory
    ):
        """Mismatched issuer raises TokenValidationError."""
        token = token_factory(iss="https://wrong-issuer.example.com/")
        validator = JWTValidator(oidc_settings)

        with pytest.raises(TokenValidationError):
            validator.validate(token)

    def test_jwks_fetch_error(self, oidc_settings, mock_jwks_client):
        """JWKS client error raises JWKSFetchError."""
        mock_jwks_client.get_signing_key_from_jwt.side_effect = pyjwt.PyJWKClientError(
            "Connection refused"
        )
        validator = JWTValidator(oidc_settings)

        with pytest.raises(JWKSFetchError, match="Connection refused"):
            validator.validate("some.invalid.token")

    def test_jwks_connection_error(self, oidc_settings, mock_jwks_client):
        """JWKS connection error raises JWKSFetchError."""
        mock_jwks_client.get_signing_key_from_jwt.side_effect = (
            pyjwt.PyJWKClientConnectionError("Timeout")
        )
        validator = JWTValidator(oidc_settings)

        with pytest.raises(JWKSFetchError, match="Timeout"):
            validator.validate("some.invalid.token")

    def test_nbf_in_future_raises_token_validation_error(
        self, oidc_settings, mock_jwks_client, token_factory
    ):
        """Token not yet valid (nbf in future) raises TokenValidationError."""
        token = token_factory(nbf=int(time.time()) + 3600)
        validator = JWTValidator(oidc_settings)

        with pytest.raises(TokenValidationError):
            validator.validate(token)

    def test_tampered_token_raises_token_validation_error(
        self, oidc_settings, mock_jwks_client, token_factory, rsa_private_key_pem
    ):
        """Token signed with wrong key raises TokenValidationError."""
        from cryptography.hazmat.primitives.asymmetric import rsa as rsa_mod
        from cryptography.hazmat.primitives import serialization

        other_key = rsa_mod.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        token = pyjwt.encode(
            {
                "sub": "auth0|user123",
                "iss": "https://auth.example.com/",
                "aud": "https://api.example.com",
                "exp": int(time.time()) + 3600,
                "nbf": int(time.time()) - 10,
            },
            other_pem,
            algorithm="RS256",
            headers={"kid": "test-key-1"},
        )

        validator = JWTValidator(oidc_settings)

        with pytest.raises(TokenValidationError):
            validator.validate(token)
