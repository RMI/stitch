"""Unit tests for the _auth package and the /auth/me route."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi_plugin import Auth0FastAPI
from starlette.testclient import TestClient

from stitch.api._auth import (
    ALL_PERMISSIONS,
    RESOURCE_READ,
    RESOURCE_WRITE,
    SOURCE_READ_ANY,
    SOURCE_WRITE,
    AuthProvider,
    StaticAuthProvider,
    TokenClaims,
    get_auth_provider,
    licensed_sources,
)
from stitch.api._auth.impl import Auth0AuthProvider, AuthSettings, check_scopes
from stitch.api.main import app
from stitch.api.settings import Settings


def _build_provider(settings: Settings) -> AuthProvider:
    get_auth_provider.cache_clear()
    with (
        patch("stitch.api._auth.impl.get_settings", return_value=settings),
        patch(
            "stitch.api._auth.impl.get_auth_settings",
            return_value=AuthSettings(domain="example.us.auth0.com", audience="aud"),
        ),
    ):
        return get_auth_provider()


@pytest.mark.parametrize(
    ("auth_disabled", "environment", "expected"),
    [
        (True, "pr-123", StaticAuthProvider),
        (True, "production", RuntimeError),
        (False, "production", Auth0AuthProvider),
    ],
)
def test_get_auth_provider_selects_provider(auth_disabled, environment, expected):
    settings = Settings(auth_disabled=auth_disabled, environment=environment)
    if expected is RuntimeError:
        with pytest.raises(RuntimeError, match="AUTH_DISABLED"):
            _build_provider(settings)
    else:
        assert isinstance(_build_provider(settings), expected)


def test_startup_fails_when_auth_disabled_in_production():
    settings = Settings(auth_disabled=True, environment="production")
    with patch("stitch.api._auth.impl.get_settings", return_value=settings):
        with pytest.raises(RuntimeError), TestClient(app):
            pass


@pytest.mark.parametrize(
    ("granted", "required", "allowed"),
    [
        ({RESOURCE_READ, RESOURCE_WRITE}, [RESOURCE_READ, RESOURCE_WRITE], True),
        ({"source:read:wm"}, [SOURCE_READ_ANY], True),
        ({RESOURCE_READ}, [SOURCE_READ_ANY], False),
        ({SOURCE_READ_ANY}, ["source:read:wm"], False),
    ],
)
def test_check_scopes(granted, required, allowed):
    if allowed:
        check_scopes(frozenset(granted), required)
    else:
        with pytest.raises(HTTPException) as exc_info:
            check_scopes(frozenset(granted), required)
        assert exc_info.value.status_code == 403


def test_check_scopes_names_missing_permissions():
    with pytest.raises(HTTPException) as exc_info:
        check_scopes(frozenset({RESOURCE_READ}), [RESOURCE_READ, RESOURCE_WRITE])
    assert exc_info.value.detail == "Missing required permission(s): resource:write"


def _auth0_provider(monkeypatch, raw: dict) -> Auth0AuthProvider:
    async def verify(_request):
        return raw

    monkeypatch.setattr(Auth0FastAPI, "require_auth", lambda self, scopes=None: verify)
    return Auth0AuthProvider(domain="example.us.auth0.com", audience="aud")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("identity", "email"),
    [
        ({"email": "e@x.com", "preferred_username": "p@x.com"}, "e@x.com"),
        ({"preferred_username": "p@x.com"}, "p@x.com"),
    ],
)
async def test_auth0_provider_maps_claims(monkeypatch, identity, email):
    raw = {
        "sub": "auth0|1",
        "name": "U",
        "permissions": [RESOURCE_READ],
        "scope": "openid source:read:wm",
        **identity,
    }
    provider = _auth0_provider(monkeypatch, raw)

    claims = await provider.require_auth([RESOURCE_READ, SOURCE_READ_ANY])(None)

    assert claims.permissions == {RESOURCE_READ, "openid", "source:read:wm"}
    assert (claims.sub, claims.name, claims.email, claims.raw) == (
        "auth0|1",
        "U",
        email,
        raw,
    )


@pytest.mark.anyio
async def test_auth0_provider_enforces_scopes(monkeypatch):
    provider = _auth0_provider(monkeypatch, {"sub": "auth0|1"})
    with pytest.raises(HTTPException) as exc_info:
        await provider.require_auth([RESOURCE_READ])(None)
    assert exc_info.value.status_code == 403


def test_licensed_sources_keeps_only_known_source_reads():
    claims = TokenClaims(
        sub="test|user",
        permissions=frozenset(
            {
                "source:read:gem",
                "source:read:wm",
                "source:read:bogus",
                SOURCE_READ_ANY,
                SOURCE_WRITE,
                RESOURCE_READ,
            }
        ),
    )
    assert licensed_sources(claims) == {"gem", "wm"}


@pytest.mark.anyio
async def test_auth_me(client, grant):
    known = (await client.get("/auth/me")).json()
    assert known["user"]["id"] == 1
    assert known["claims"]["permissions"] == sorted(ALL_PERMISSIONS)

    grant({RESOURCE_READ}, sub="auth0|unknown")
    response = await client.get("/auth/me")

    assert response.json() == {
        "user": None,
        "claims": {
            "sub": "auth0|unknown",
            "email": "test@test.com",
            "name": "Test User",
            "permissions": [RESOURCE_READ],
            "raw": {},
        },
    }
