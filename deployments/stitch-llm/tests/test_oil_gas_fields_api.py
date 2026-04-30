from __future__ import annotations

from contextlib import AbstractAsyncContextManager

import pytest
from fastapi.testclient import TestClient
from stitch.client import StitchAPIError

from stitch.llm.auth import get_current_user
from stitch.llm.azure_responses import AzureResponsesResult
from stitch.llm.entities import User
from stitch.llm.errors import LLMConfigurationError
from stitch.llm.main import app
from stitch.llm import auth as auth_module
from stitch.llm.routers import oil_gas_fields as route_module
from stitch.llm.settings import Settings, get_settings
from stitch.ogsi.model import GemSource, OGFieldDetailView
from stitch.ogsi.model.og_field import OilGasFieldBase


def make_detail_view(**data) -> OGFieldDetailView:
    return OGFieldDetailView(
        id=42,
        data=OilGasFieldBase(name="Alpha", country="USA", **data),
        provenance={},
        source_data=[
            GemSource(source="gem", name="Alpha", country="USA", **data),
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


@pytest.fixture
def test_client(monkeypatch: pytest.MonkeyPatch):
    async def override_current_user() -> User:
        return User(
            id=1,
            sub="test|user",
            email="test@example.com",
            name="Test User",
        )

    test_settings = Settings(
        auth_disabled=True,
        azure_openai_base_url=None,
        azure_openai_api_key=None,
        azure_openai_model=None,
    )
    monkeypatch.setattr(auth_module, "get_settings", lambda: test_settings)
    monkeypatch.setattr(route_module, "get_settings", lambda: test_settings)
    app.dependency_overrides[get_current_user] = override_current_user

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
    monkeypatch.setattr(route_module, "StitchApiClient", lambda: stitch_client)
    monkeypatch.setattr(route_module, "AzureResponsesClient", lambda: azure_client)
    return azure_client


def override_settings_for_test(monkeypatch: pytest.MonkeyPatch, **overrides) -> None:
    settings = get_settings().model_copy(update=overrides)
    monkeypatch.setattr(route_module, "get_settings", lambda: settings)


def test_get_suggestion_returns_validated_value(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    override_settings_for_test(monkeypatch, auth_disabled=False)
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

    response = test_client.get("/api/v1/oil-gas-fields/42?field=basin")

    assert response.status_code == 200
    assert response.json() == {
        "resource_id": 42,
        "field": "basin",
        "value": "Permian Basin",
        "citations": [
            {"url": "https://example.com/article", "title": "Example Article"}
        ],
        "query_succeeded": True,
        "model": "test-model",
        "rationale": "Public sources identify the basin.",
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


def test_get_suggestion_returns_409_when_field_populated(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stitch_client = FakeStitchApiClient(
        detail_view=make_detail_view(basin="Permian Basin")
    )
    azure_client = install_fakes(monkeypatch, stitch_client=stitch_client)

    response = test_client.get("/api/v1/oil-gas-fields/42?field=basin")

    assert response.status_code == 409
    assert azure_client.calls == []


def test_get_suggestion_maps_stitch_404(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stitch_client = FakeStitchApiClient(
        error=StitchAPIError("missing", status_code=404)
    )
    install_fakes(monkeypatch, stitch_client=stitch_client)

    response = test_client.get("/api/v1/oil-gas-fields/42?field=basin")

    assert response.status_code == 404


def test_get_suggestion_maps_missing_azure_config(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stitch_client = FakeStitchApiClient(detail_view=make_detail_view(basin=None))
    override_settings_for_test(monkeypatch, auth_disabled=False)
    install_fakes(
        monkeypatch,
        stitch_client=stitch_client,
        azure_client=FakeAzureResponsesClient(
            error=LLMConfigurationError("Azure OpenAI settings are not configured.")
        ),
    )

    response = test_client.get("/api/v1/oil-gas-fields/42?field=basin")

    assert response.status_code == 503


def test_get_suggestion_returns_placeholder_when_auth_disabled_and_azure_missing(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stitch_client = FakeStitchApiClient(detail_view=make_detail_view(basin=None))
    override_settings_for_test(
        monkeypatch,
        auth_disabled=True,
        azure_openai_base_url=None,
        azure_openai_api_key=None,
        azure_openai_model=None,
    )
    azure_client = install_fakes(monkeypatch, stitch_client=stitch_client)

    response = test_client.get("/api/v1/oil-gas-fields/42?field=basin")

    assert response.status_code == 200
    assert response.json()["value"] == ":warning: placeholder LLM value"
    assert response.json()["citations"] == []
    assert response.json()["model"] == "placeholder-llm"
    assert azure_client.calls == []


def test_get_suggestion_returns_null_for_non_string_placeholder_fallback(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stitch_client = FakeStitchApiClient(
        detail_view=make_detail_view(discovery_year=None)
    )
    override_settings_for_test(
        monkeypatch,
        auth_disabled=True,
        azure_openai_base_url=None,
        azure_openai_api_key=None,
        azure_openai_model=None,
    )
    azure_client = install_fakes(monkeypatch, stitch_client=stitch_client)

    response = test_client.get("/api/v1/oil-gas-fields/42?field=discovery_year")

    assert response.status_code == 200
    assert response.json()["value"] is None
    assert response.json()["citations"] == []
    assert response.json()["model"] == "placeholder-llm"
    assert azure_client.calls == []


def test_get_suggestion_maps_invalid_model_output(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    override_settings_for_test(monkeypatch, auth_disabled=False)
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
                "output_text": "VALUE: Subsea\nRATIONALE: Public sources identify the location type.",
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

    response = test_client.get("/api/v1/oil-gas-fields/42?field=location_type")

    assert response.status_code == 502


def test_get_suggestion_returns_null_when_no_public_citation_found(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    override_settings_for_test(monkeypatch, auth_disabled=False)
    stitch_client = FakeStitchApiClient(detail_view=make_detail_view(basin=None))
    install_fakes(
        monkeypatch,
        stitch_client=stitch_client,
        azure_client=FakeAzureResponsesClient(
            output_text="VALUE: Permian Basin\nRATIONALE: I could not verify the basin with public citations."
        ),
    )

    response = test_client.get("/api/v1/oil-gas-fields/42?field=basin")

    assert response.status_code == 200
    assert response.json()["value"] is None
    assert response.json()["citations"] == []
    assert response.json()["query_succeeded"] is True


def test_get_suggestion_returns_null_when_annotations_absent(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    override_settings_for_test(monkeypatch, auth_disabled=False)
    output_text = (
        "VALUE: Songliao Basin\n"
        "RATIONALE: Public sources describing Daqing Oil Field place it in the Songliao Basin."
    )
    stitch_client = FakeStitchApiClient(detail_view=make_detail_view(basin=None))
    install_fakes(
        monkeypatch,
        stitch_client=stitch_client,
        azure_client=FakeAzureResponsesClient(
            output_text=output_text,
            response_payload={
                "id": "resp_test",
                "model": "test-model",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "annotations": [],
                                "text": output_text,
                            }
                        ],
                    }
                ],
            },
        ),
    )

    response = test_client.get("/api/v1/oil-gas-fields/42?field=basin")

    assert response.status_code == 200
    assert response.json()["value"] is None
    assert response.json()["citations"] == []
    assert (
        response.json()["rationale"]
        == "Public sources describing Daqing Oil Field place it in the Songliao Basin."
    )
    assert response.json()["query_succeeded"] is True
