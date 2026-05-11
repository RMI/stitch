from __future__ import annotations

from contextlib import AbstractAsyncContextManager

import pytest
from fastapi.testclient import TestClient

from stitch.client import StitchAPIError
from stitch.llm import main as main_module
from stitch.llm.main import app
from stitch.llm.routers import health as health_module
from stitch.llm.settings import Settings


class FakeStitchApiClient(AbstractAsyncContextManager["FakeStitchApiClient"]):
    def __init__(
        self,
        *,
        auth_me_response: dict | None = None,
        auth_me_error: Exception | None = None,
    ) -> None:
        self.auth_me_response = auth_me_response or {"claims": {"sub": "auth0|llm"}}
        self.auth_me_error = auth_me_error
        self.auth_me_calls = 0

    async def __aenter__(self) -> "FakeStitchApiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get_auth_me(self) -> dict:
        self.auth_me_calls += 1
        if self.auth_me_error is not None:
            raise self.auth_me_error
        return self.auth_me_response


@pytest.fixture
def test_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main_module, "validate_auth_config_at_startup", lambda: None)
    monkeypatch.setattr(
        main_module, "validate_downstream_auth_config_at_startup", lambda: None
    )

    with TestClient(app) as client:
        yield client


def test_health_details_reports_ready_when_downstream_and_llm_are_configured(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        health_module,
        "get_settings",
        lambda: Settings(
            auth_disabled=False,
            azure_openai_base_url="https://example.openai.azure.com/openai/v1",
            azure_openai_api_key="azure-key",
            azure_openai_model="model",
        ),
    )
    fake_client = FakeStitchApiClient(
        auth_me_response={"claims": {"sub": "auth0|ready-llm"}}
    )
    monkeypatch.setattr(health_module, "StitchApiClient", lambda: fake_client)

    response = test_client.get("/api/v1/health/details")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["ready"] is True
    assert response.json()["downstream_api"]["token_accepted"] is True
    assert response.json()["downstream_api"]["has_error"] is False
    assert response.json()["downstream_api"]["error_code"] is None
    assert response.json()["llm_backend"]["configured"] is True
    assert response.json()["llm_backend"]["placeholder_mode"] is False
    assert fake_client.auth_me_calls == 1


def test_health_details_reports_not_ready_when_downstream_probe_fails(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        health_module,
        "get_settings",
        lambda: Settings(
            auth_disabled=False,
            azure_openai_base_url="https://example.openai.azure.com/openai/v1",
            azure_openai_api_key="azure-key",
            azure_openai_model="model",
        ),
    )
    fake_client = FakeStitchApiClient(
        auth_me_error=StitchAPIError(
            "GET /auth/me failed with status 401: unauthorized",
            status_code=401,
            response_text="unauthorized",
        )
    )
    monkeypatch.setattr(health_module, "StitchApiClient", lambda: fake_client)

    response = test_client.get("/api/v1/health/details")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["ready"] is False
    assert response.json()["downstream_api"]["token_accepted"] is False
    assert response.json()["downstream_api"]["ready"] is False
    assert response.json()["downstream_api"]["has_error"] is True
    assert response.json()["downstream_api"]["error_code"] == "downstream_401"
    assert response.json()["downstream_api"]["http_status"] == 401
