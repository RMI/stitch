"""End-to-end M2M auth: a real Auth0-style token through the full HTTP path.

Unlike ``test_auth_integration.py`` (which calls ``get_current_user`` directly),
this drives stitch-client's ``Auth0M2MAuth`` — with the token fetched from a
mocked Auth0 ``/oauth/token`` — against the real ASGI app. It exercises the
Authorization-header → ``JWTValidator`` (JWKS) → ``require_permissions`` → route
→ DB path that the direct-call tests bypass, proving the deployed
client-credentials flow is accepted end to end.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jwt import PyJWK
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import select

from stitch.auth.permissions import ALL_PERMISSIONS, RESOURCE_WRITE
from stitch.client import Auth0M2MAuth, StitchClientConfig
from stitch.client.auth import fetch_auth_jwt

from stitch.api.auth import get_jwt_validator, get_oidc_settings
from stitch.api.db.config import UnitOfWork, get_session_factory, get_uow
from stitch.api.db.model.user import User as UserModel
from stitch.api.main import app
from stitch.api.settings import get_settings

_ISSUER = "https://auth.example.com/"
_AUDIENCE = "https://api.example.com"
_JWKS_URI = "https://auth.example.com/.well-known/jwks.json"
_KID = "test-key-1"
_M2M_SUB = "svcClientAbc123@clients"


@pytest.fixture
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def private_pem(rsa_key: rsa.RSAPrivateKey) -> bytes:
    return rsa_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


@pytest.fixture
def public_jwk(rsa_key: rsa.RSAPrivateKey) -> dict[str, Any]:
    jwk = RSAAlgorithm.to_jwk(rsa_key.public_key(), as_dict=True)
    jwk["kid"] = _KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return jwk


@pytest.fixture
def real_auth_env(
    monkeypatch: pytest.MonkeyPatch,
    public_jwk: dict[str, Any],
) -> Iterator[None]:
    """Enable real auth: set OIDC env, reset caches, patch the JWKS client."""
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("AUTH_ISSUER", _ISSUER)
    monkeypatch.setenv("AUTH_AUDIENCE", _AUDIENCE)
    monkeypatch.setenv("AUTH_JWKS_URI", _JWKS_URI)
    get_settings.cache_clear()
    get_oidc_settings.cache_clear()
    get_jwt_validator.cache_clear()

    mock_jwks = MagicMock()
    mock_jwks.get_signing_key_from_jwt.return_value = PyJWK.from_dict(public_jwk)
    with patch("stitch.auth.validator.PyJWKClient", return_value=mock_jwks):
        yield


def _mint_m2m_token(private_pem: bytes, *, permissions: list[str]) -> str:
    """Sign an Auth0 client-credentials-style access token with the test key."""
    now = int(time.time())
    payload = {
        "sub": _M2M_SUB,
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "exp": now + 3600,
        "iat": now,
        "gty": "client-credentials",
        "azp": "svcClientAbc123",
        "permissions": permissions,
    }
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": _KID})


def _m2m_httpx_client(token: str) -> AsyncClient:
    """AsyncClient that fetches ``token`` via a mocked Auth0 /oauth/token."""
    config = StitchClientConfig(
        client_id="cid",
        client_secret="csec",
        audience=_AUDIENCE,
        auth_issuer_url=_ISSUER,
        api_base_url="http://test/api/v1",
    )
    oauth_transport = httpx.MockTransport(
        lambda _req: httpx.Response(200, json={"access_token": token})
    )

    async def _fetch() -> str:
        return await fetch_auth_jwt(config, transport=oauth_transport)

    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test/api/v1",
        auth=Auth0M2MAuth(_fetch),
    )


def _valid_resource_payload() -> dict[str, Any]:
    return {
        "id": None,
        "source_data": [
            {
                "id": None,
                "source": "gem",
                "name": "M2M Field",
                "country": "USA",
                "source_record": {
                    "observed_at": "2026-01-01T00:00:00Z",
                    "producer": "test",
                    "payload": {"kind": "fixture"},
                },
            }
        ],
        "constituents": [],
    }


@pytest.fixture
def m2m_db_overrides(integration_session_factory) -> Iterator[None]:
    """Point both get_uow and get_current_user's session factory at SQLite."""

    async def override_get_uow() -> AsyncIterator[UnitOfWork]:
        async with UnitOfWork(integration_session_factory) as uow:
            yield uow

    app.dependency_overrides[get_uow] = override_get_uow
    app.dependency_overrides[get_session_factory] = lambda: integration_session_factory
    yield
    # reset_dependency_overrides (autouse) clears these after the test.


@pytest.mark.anyio
async def test_m2m_token_accepted_and_jit_provisions_user(
    private_pem: bytes,
    integration_session_factory,
    real_auth_env: None,
    m2m_db_overrides: None,
) -> None:
    token = _mint_m2m_token(private_pem, permissions=sorted(ALL_PERMISSIONS))

    async with _m2m_httpx_client(token) as client:
        response = await client.post("/oil-gas-fields/", json=_valid_resource_payload())

    assert response.status_code == 200, response.text

    async with integration_session_factory() as session:
        row = (
            await session.execute(select(UserModel).where(UserModel.sub == _M2M_SUB))
        ).scalar_one()
    assert row.sub == _M2M_SUB
    # M2M subs carry no name/email — JIT row is provisioned with nulls.
    assert row.name is None
    assert row.email is None


@pytest.mark.anyio
async def test_m2m_token_missing_write_permission_is_forbidden(
    private_pem: bytes,
    real_auth_env: None,
    m2m_db_overrides: None,
) -> None:
    permissions = sorted(ALL_PERMISSIONS - {RESOURCE_WRITE})
    token = _mint_m2m_token(private_pem, permissions=permissions)

    async with _m2m_httpx_client(token) as client:
        response = await client.post("/oil-gas-fields/", json=_valid_resource_payload())

    # Token is valid (authenticated) but lacks resource:write → 403, not 401.
    assert response.status_code == 403, response.text
