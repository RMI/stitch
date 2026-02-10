"""Pytest fixtures for stitch-auth tests.

Provides an RSA keypair, JWKS endpoint mock, and a token factory
for testing JWTValidator without hitting real OIDC providers.
"""

import time
from typing import Any
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from jwt import PyJWK
from jwt.algorithms import RSAAlgorithm

from stitch.auth.settings import OIDCSettings


@pytest.fixture
def rsa_private_key() -> rsa.RSAPrivateKey:
    """Generate a fresh RSA private key for signing test tokens."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def rsa_private_key_pem(rsa_private_key: rsa.RSAPrivateKey) -> bytes:
    """PEM-encoded private key for PyJWT signing."""
    return rsa_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


@pytest.fixture
def rsa_public_jwk(rsa_private_key: rsa.RSAPrivateKey) -> dict[str, Any]:
    """JWK dict for the public key (as returned by a JWKS endpoint)."""
    public_key = rsa_private_key.public_key()
    jwk_dict = RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk_dict["kid"] = "test-key-1"
    jwk_dict["use"] = "sig"
    jwk_dict["alg"] = "RS256"
    return jwk_dict


@pytest.fixture
def oidc_settings() -> OIDCSettings:
    """OIDC settings for tests — auth enabled with test values."""
    return OIDCSettings(
        issuer="https://test.auth0.com/",
        audience="https://api.test.example.com",
        jwks_uri="https://test.auth0.com/.well-known/jwks.json",
        algorithms=("RS256",),
        clock_skew_seconds=30,
        disabled=False,
    )


@pytest.fixture
def token_factory(rsa_private_key_pem: bytes):
    """Factory that creates signed JWTs with configurable claims."""

    def _make_token(
        sub: str = "auth0|user123",
        email: str | None = "user@example.com",
        name: str | None = "Test User",
        iss: str = "https://test.auth0.com/",
        aud: str = "https://api.test.example.com",
        exp: int | None = None,
        nbf: int | None = None,
        iat: int | None = None,
        kid: str = "test-key-1",
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        now = int(time.time())
        payload: dict[str, Any] = {
            "sub": sub,
            "iss": iss,
            "aud": aud,
            "exp": exp if exp is not None else now + 3600,
            "nbf": nbf if nbf is not None else now - 10,
            "iat": iat if iat is not None else now,
        }
        if email is not None:
            payload["email"] = email
        if name is not None:
            payload["name"] = name
        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(
            payload,
            rsa_private_key_pem,
            algorithm="RS256",
            headers={"kid": kid},
        )

    return _make_token


@pytest.fixture
def mock_jwks_client(rsa_public_jwk: dict[str, Any]):
    """Patches PyJWKClient.get_signing_key_from_jwt to return our test key."""
    signing_key = PyJWK.from_dict(rsa_public_jwk)

    mock_client = MagicMock()
    mock_client.get_signing_key_from_jwt.return_value = signing_key

    with patch(
        "stitch.auth.validator.PyJWKClient", return_value=mock_client
    ) as mock_cls:
        mock_cls._instance = mock_client
        yield mock_client
