from __future__ import annotations

import json
import time
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from stitch.auth import TokenClaims
from stitch.auth.permissions import SERVICE_LLM_SUGGEST
from stitch.client import StitchAPIError
from stitch.ogsi.model import GemSource, OGFieldDetailView, SourceRecord
from stitch.ogsi.model.og_field import OilGasFieldBase
from stitch.service.auth import RequestAuthContext

from stitch.llm import auth as auth_module
from stitch.llm import jobs as jobs_module
from stitch.llm import main as main_module
from stitch.llm.auth import get_request_auth_context, get_token_claims
from stitch.llm.azure_responses import AzureResponsesResult
from stitch.llm.entities import User
from stitch.llm.errors import LLMConfigurationError
from stitch.llm.main import app
from stitch.llm.routers.oil_gas_fields import get_job_manager
from stitch.llm.settings import Settings


def make_detail_view(**data) -> OGFieldDetailView:
    return OGFieldDetailView(
        id=42,
        data=OilGasFieldBase(name="Alpha", country="USA", **data),
        provenance={},
        source_data=[
            GemSource(
                source="gem",
                name="Alpha",
                country="USA",
                source_record=SourceRecord(
                    observed_at=datetime(2026, 1, 1, tzinfo=UTC),
                    producer="test",
                    payload={"kind": "fixture"},
                ),
                **data,
            ),
        ],
    )


class FakeStitchApiClient(AbstractAsyncContextManager["FakeStitchApiClient"]):
    def __init__(
        self,
        *,
        detail_view: OGFieldDetailView | None = None,
        error: Exception | None = None,
    ) -> None:
        self.detail_view = detail_view
        self.error = error
        self.detail_calls: list[int] = []

    async def __aenter__(self) -> "FakeStitchApiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get_oil_gas_field_detail(self, resource_id: int) -> OGFieldDetailView:
        self.detail_calls.append(resource_id)
        if self.error is not None:
            raise self.error
        assert self.detail_view is not None
        return self.detail_view


class FakeAzureResponsesClient(AbstractAsyncContextManager["FakeAzureResponsesClient"]):
    def __init__(
        self,
        *,
        output_text: str = "VALUE: Permian Basin\nRATIONALE: Public sources identify the basin.",
        model: str = "test-model",
        response_payload: dict | None = None,
        error: Exception | None = None,
    ) -> None:
        self.output_text = output_text
        self.model = model
        self.response_payload = response_payload
        self.error = error
        self.calls: list[dict] = []

    async def __aenter__(self) -> "FakeAzureResponsesClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def generate_field_suggestion(self, *, field, input_messages):
        self.calls.append({"field": field, "input_messages": input_messages})
        if self.error is not None:
            raise self.error
        return AzureResponsesResult(
            output_text=self.output_text,
            model=self.model,
            request_payload={
                "model": self.model,
                "input": input_messages,
                "store": False,
                "tools": [{"type": "web_search"}],
            },
            response_payload=self.response_payload
            or {
                "id": "resp_test",
                "model": self.model,
                "output_text": self.output_text,
            },
        )


def _settings(*, auth_disabled: bool) -> Settings:
    return Settings(
        auth_disabled=auth_disabled,
        azure_openai_base_url=None,
        azure_openai_api_key=None,
        azure_openai_model=None,
    )


@pytest.fixture(autouse=True)
def reset_job_manager():
    get_job_manager().reset()
    yield
    get_job_manager().reset()


@pytest.fixture
def test_client(monkeypatch: pytest.MonkeyPatch):
    # Default: auth-disabled, Azure unconfigured (placeholder mode for the job).
    # Patch auth's settings too, so startup auth validation short-circuits
    # instead of building OIDCSettings (which has no env config in CI).
    test_settings = _settings(auth_disabled=True)
    monkeypatch.setattr(jobs_module, "get_settings", lambda: test_settings)
    monkeypatch.setattr(auth_module, "get_settings", lambda: test_settings)
    monkeypatch.setattr(
        main_module, "validate_downstream_auth_config_at_startup", lambda: None
    )

    def override_token_claims() -> TokenClaims:
        return TokenClaims(
            sub="test|user", permissions=frozenset({SERVICE_LLM_SUGGEST})
        )

    async def override_request_auth_context() -> RequestAuthContext:
        return RequestAuthContext(
            user=User(
                id=1, sub="test|user", email="test@example.com", name="Test User"
            ),
            bearer_token="test-token",
        )

    app.dependency_overrides[get_token_claims] = override_token_claims
    app.dependency_overrides[get_request_auth_context] = override_request_auth_context

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stitch_client: FakeStitchApiClient,
    azure_client: FakeAzureResponsesClient | None = None,
) -> FakeAzureResponsesClient:
    azure_client = azure_client or FakeAzureResponsesClient()
    monkeypatch.setattr(jobs_module, "StitchApiClient", lambda: stitch_client)
    monkeypatch.setattr(jobs_module, "AzureResponsesClient", lambda: azure_client)
    return azure_client


def enable_foundry_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        jobs_module, "get_settings", lambda: _settings(auth_disabled=False)
    )


def _start(
    client: TestClient, *, resource_id: int = 42, field: str = "basin", force=False
):
    return client.post(
        "/api/v1/oil-gas-fields/start",
        json={"resource_id": resource_id, "field": field, "force": force},
    )


def _poll(client: TestClient, job_id: str, *, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/v1/oil-gas-fields/status/{job_id}").json()
        if body["state"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError("job did not finish within timeout")


def _run(client: TestClient, **kwargs) -> dict:
    started = _start(client, **kwargs)
    assert started.status_code == 202
    return _poll(client, started.json()["job_id"])


def test_start_requires_service_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_settings = _settings(auth_disabled=True)
    monkeypatch.setattr(jobs_module, "get_settings", lambda: test_settings)
    monkeypatch.setattr(auth_module, "get_settings", lambda: test_settings)
    monkeypatch.setattr(
        main_module, "validate_downstream_auth_config_at_startup", lambda: None
    )

    def override_token_claims() -> TokenClaims:
        return TokenClaims(sub="test|user", permissions=frozenset())

    async def override_request_auth_context() -> RequestAuthContext:
        return RequestAuthContext(
            user=User(id=1, sub="test|user", email="t@example.com", name="T"),
            bearer_token="x",
        )

    app.dependency_overrides[get_token_claims] = override_token_claims
    app.dependency_overrides[get_request_auth_context] = override_request_auth_context

    with TestClient(app) as client:
        response = _start(client)

    app.dependency_overrides.clear()

    assert response.status_code == 403
    assert SERVICE_LLM_SUGGEST in response.json()["detail"]


def test_job_returns_validated_value(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_foundry_mode(monkeypatch)
    stitch_client = FakeStitchApiClient(detail_view=make_detail_view(basin=None))
    azure_client = install_fakes(
        monkeypatch,
        stitch_client=stitch_client,
        azure_client=FakeAzureResponsesClient(
            output_text="VALUE:   Permian Basin  \nRATIONALE: Public sources identify the basin.",
            response_payload={
                "id": "resp_test",
                "model": "test-model",
                "output_text": "VALUE:   Permian Basin  \nRATIONALE: Public sources identify the basin.",
                "output": [
                    {
                        "content": [
                            {
                                "annotations": [
                                    {
                                        "type": "url_citation",
                                        "url": "https://example.com/article",
                                        "title": "Example Article",
                                    }
                                ]
                            }
                        ]
                    }
                ],
            },
        ),
    )

    final = _run(test_client)
    assert final["state"] == "succeeded"
    result = final["result"]
    assert result["observed_at"].endswith("Z")
    prompt_payload = json.loads(azure_client.calls[0]["input_messages"][1]["content"])
    assert "source_record" not in prompt_payload["source_records"][0]
    assert result == {
        "resource_id": 42,
        "field": "basin",
        "value": "Permian Basin",
        "citations": [
            {"url": "https://example.com/article", "title": "Example Article"}
        ],
        "query_succeeded": True,
        "model": "test-model",
        "rationale": "Public sources identify the basin.",
        "observed_at": result["observed_at"],
        "foundry_request": {
            "model": "test-model",
            "input": azure_client.calls[0]["input_messages"],
            "store": False,
            "tools": [{"type": "web_search"}],
        },
        "foundry_response": {
            "id": "resp_test",
            "model": "test-model",
            "output_text": "VALUE:   Permian Basin  \nRATIONALE: Public sources identify the basin.",
            "output": [
                {
                    "content": [
                        {
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://example.com/article",
                                    "title": "Example Article",
                                }
                            ]
                        }
                    ]
                }
            ],
        },
    }
    assert stitch_client.detail_calls == [42]
    assert azure_client.calls[0]["field"] == "basin"


def test_job_fails_when_field_populated(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stitch_client = FakeStitchApiClient(
        detail_view=make_detail_view(basin="Permian Basin")
    )
    azure_client = install_fakes(monkeypatch, stitch_client=stitch_client)

    final = _run(test_client)
    assert final["state"] == "failed"
    assert final["error"]
    assert azure_client.calls == []


def test_job_fails_on_stitch_404(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stitch_client = FakeStitchApiClient(
        error=StitchAPIError("missing", status_code=404)
    )
    install_fakes(monkeypatch, stitch_client=stitch_client)

    final = _run(test_client)
    assert final["state"] == "failed"
    assert "missing" in final["error"]


def test_job_fails_on_missing_azure_config(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_foundry_mode(monkeypatch)
    stitch_client = FakeStitchApiClient(detail_view=make_detail_view(basin=None))
    install_fakes(
        monkeypatch,
        stitch_client=stitch_client,
        azure_client=FakeAzureResponsesClient(
            error=LLMConfigurationError("Azure OpenAI settings are not configured.")
        ),
    )

    final = _run(test_client)
    assert final["state"] == "failed"
    assert "Azure OpenAI" in final["error"]


def test_job_placeholder_when_auth_disabled_and_azure_missing(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stitch_client = FakeStitchApiClient(detail_view=make_detail_view(basin=None))
    azure_client = install_fakes(monkeypatch, stitch_client=stitch_client)

    final = _run(test_client)
    assert final["state"] == "succeeded"
    result = final["result"]
    assert result["value"] == ":warning: placeholder LLM value"
    assert result["citations"] == []
    assert result["model"] == "placeholder-llm"
    assert result["observed_at"].endswith("Z")
    assert azure_client.calls == []


def test_job_null_for_non_string_placeholder_fallback(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stitch_client = FakeStitchApiClient(
        detail_view=make_detail_view(discovery_year=None)
    )
    azure_client = install_fakes(monkeypatch, stitch_client=stitch_client)

    final = _run(test_client, field="discovery_year")
    assert final["state"] == "succeeded"
    result = final["result"]
    assert result["value"] is None
    assert result["model"] == "placeholder-llm"
    assert azure_client.calls == []


def test_job_fails_on_invalid_model_output(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_foundry_mode(monkeypatch)
    stitch_client = FakeStitchApiClient(
        detail_view=make_detail_view(location_type=None)
    )
    install_fakes(
        monkeypatch,
        stitch_client=stitch_client,
        azure_client=FakeAzureResponsesClient(
            output_text="VALUE: Subsea\nRATIONALE: Public sources identify the location type.",
            response_payload={
                "id": "resp_test",
                "model": "test-model",
                "output_text": "VALUE: Subsea\nRATIONALE: ...",
                "output": [
                    {
                        "content": [
                            {
                                "annotations": [
                                    {
                                        "type": "url_citation",
                                        "url": "https://example.com/article",
                                        "title": "Example Article",
                                    }
                                ]
                            }
                        ]
                    }
                ],
            },
        ),
    )

    final = _run(test_client, field="location_type")
    assert final["state"] == "failed"


def test_job_null_when_no_public_citation_found(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_foundry_mode(monkeypatch)
    stitch_client = FakeStitchApiClient(detail_view=make_detail_view(basin=None))
    install_fakes(
        monkeypatch,
        stitch_client=stitch_client,
        azure_client=FakeAzureResponsesClient(
            output_text="VALUE: Permian Basin\nRATIONALE: I could not verify the basin with public citations."
        ),
    )

    final = _run(test_client)
    assert final["state"] == "succeeded"
    result = final["result"]
    assert result["value"] is None
    assert result["citations"] == []
    assert result["query_succeeded"] is True


# --------------------------------------------------------------------------- #
# Job-specific behavior: dedup per (resource_id, field), force, failed-retry
# --------------------------------------------------------------------------- #


def test_same_resource_field_reuses_existing_job(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stitch_client = FakeStitchApiClient(detail_view=make_detail_view(basin=None))
    install_fakes(monkeypatch, stitch_client=stitch_client)

    first = _start(test_client)
    job_id = first.json()["job_id"]
    _poll(test_client, job_id)

    # Same (resource_id, field) → reused (200, same job), even for a new caller.
    second = _start(test_client)
    assert second.status_code == 200
    assert second.json()["job_id"] == job_id


def test_distinct_pairs_get_distinct_jobs(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stitch_client = FakeStitchApiClient(detail_view=make_detail_view(basin=None))
    install_fakes(monkeypatch, stitch_client=stitch_client)

    a = _start(test_client, field="basin")
    b = _start(test_client, field="state_province")
    assert a.status_code == 202 and b.status_code == 202
    assert a.json()["job_id"] != b.json()["job_id"]


def test_force_starts_a_new_run(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stitch_client = FakeStitchApiClient(detail_view=make_detail_view(basin=None))
    install_fakes(monkeypatch, stitch_client=stitch_client)

    first = _start(test_client)
    _poll(test_client, first.json()["job_id"])

    forced = _start(test_client, force=True)
    assert forced.status_code == 202
    assert forced.json()["job_id"] != first.json()["job_id"]
    _poll(test_client, forced.json()["job_id"])


def test_failed_pair_auto_retries(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stitch_client = FakeStitchApiClient(error=StitchAPIError("boom", status_code=500))
    install_fakes(monkeypatch, stitch_client=stitch_client)

    first = _start(test_client)
    first_final = _poll(test_client, first.json()["job_id"])
    assert first_final["state"] == "failed"

    # Failed runs are not reused → the next request retries with a new job.
    second = _start(test_client)
    assert second.status_code == 202
    assert second.json()["job_id"] != first.json()["job_id"]
    _poll(test_client, second.json()["job_id"])
