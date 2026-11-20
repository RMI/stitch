from types import SimpleNamespace

import pytest
from fastapi import Request

from stitch.llm import auth as auth_module
from stitch.llm.auth import SERVICE_LLM_SUGGEST, TokenClaims, get_token_claims
from stitch.llm.settings import Settings


@pytest.mark.anyio
async def test_get_token_claims_returns_claims_for_valid_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = {"sub": "auth0|1", "name": "U", "permissions": [SERVICE_LLM_SUGGEST]}

    async def verify(_request: Request) -> dict:
        return raw

    monkeypatch.setattr(
        auth_module, "get_settings", lambda: Settings(auth_disabled=False)
    )
    monkeypatch.setattr(
        auth_module, "get_auth0", lambda: SimpleNamespace(require_auth=lambda: verify)
    )
    request = Request({"type": "http", "headers": [(b"authorization", b"Bearer t")]})

    claims = await get_token_claims(request)

    assert claims == TokenClaims(
        sub="auth0|1", name="U", permissions=frozenset({SERVICE_LLM_SUGGEST}), raw=raw
    )
