import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from stitch.auth import SOURCE_WRITE, TokenClaims

from stitch.service.auth import (
    AuthMode,
    ServiceAuth,
    build_headers_provider,
    machine_token_headers_provider,
    relay_token_headers_provider,
)
from stitch.client.auth import STITCH_CLIENT_BEARER_TOKEN_ENV_VAR


# --------------------------------------------------------------------------- #
# Downstream auth seam
# --------------------------------------------------------------------------- #


def test_machine_provider_reads_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STITCH_CLIENT_BEARER_TOKEN_ENV_VAR, "machine-tok")
    provider = build_headers_provider(AuthMode.machine)
    assert provider() == {"Authorization": "Bearer machine-tok"}
    # Sanity: the helper and the dispatcher agree.
    assert machine_token_headers_provider()() == {"Authorization": "Bearer machine-tok"}


def test_machine_provider_requires_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(STITCH_CLIENT_BEARER_TOKEN_ENV_VAR, raising=False)
    provider = build_headers_provider(AuthMode.machine)
    with pytest.raises(ValueError):
        provider()


def test_passthrough_provider_relays_caller_token() -> None:
    provider = build_headers_provider(AuthMode.passthrough, token="caller-jwt")
    assert provider() == {"Authorization": "Bearer caller-jwt"}
    assert relay_token_headers_provider("x")() == {"Authorization": "Bearer x"}


def test_passthrough_requires_token() -> None:
    with pytest.raises(ValueError):
        build_headers_provider(AuthMode.passthrough)


# --------------------------------------------------------------------------- #
# Inbound auth
# --------------------------------------------------------------------------- #


def build_app(auth: ServiceAuth) -> FastAPI:
    app = FastAPI()

    @app.get("/me")
    async def me(user: auth.CurrentUser):
        return {"sub": user.sub, "name": user.name}

    @app.get("/context")
    async def context(ctx: auth.AuthContext):
        return {"sub": ctx.user.sub, "bearer_token": ctx.bearer_token}

    @app.post(
        "/guarded",
        dependencies=[Depends(auth.require_permissions(SOURCE_WRITE))],
    )
    async def guarded():
        return {"ok": True}

    return app


def test_auth_disabled_resolves_dev_user_without_a_token() -> None:
    auth = ServiceAuth(is_auth_disabled=lambda: True)
    app = build_app(auth)

    with TestClient(app) as client:
        me = client.get("/me")
        assert me.status_code == 200
        assert me.json()["sub"] == "dev|local-placeholder"

        # Dev claims carry all permissions, so the guarded route is allowed.
        assert client.post("/guarded").status_code == 200

        # In disabled mode the relayed token is the dev placeholder.
        ctx = client.get("/context")
        assert ctx.json()["bearer_token"] == "dev-placeholder-token"


def test_require_permissions_rejects_missing_permission() -> None:
    auth = ServiceAuth(is_auth_disabled=lambda: False)
    app = build_app(auth)

    def claims_without_permission() -> TokenClaims:
        return TokenClaims(sub="user|1", permissions=frozenset())

    app.dependency_overrides[auth.get_token_claims] = claims_without_permission

    with TestClient(app) as client:
        response = client.post("/guarded")

    assert response.status_code == 403
    assert SOURCE_WRITE in response.json()["detail"]


def test_request_context_relays_caller_bearer_token() -> None:
    auth = ServiceAuth(is_auth_disabled=lambda: False)
    app = build_app(auth)

    def claims() -> TokenClaims:
        return TokenClaims(sub="user|1", permissions=frozenset({SOURCE_WRITE}))

    app.dependency_overrides[auth.get_token_claims] = claims

    with TestClient(app) as client:
        response = client.get(
            "/context", headers={"Authorization": "Bearer caller-jwt"}
        )

    assert response.status_code == 200
    assert response.json()["bearer_token"] == "caller-jwt"
