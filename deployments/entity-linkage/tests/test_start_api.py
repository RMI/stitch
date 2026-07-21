from __future__ import annotations

from contextlib import AbstractAsyncContextManager

import pytest
from fastapi.testclient import TestClient

from stitch.auth import TokenClaims
from stitch.auth.permissions import SERVICE_ENTITY_LINKAGE_RUN
from stitch.entity_linkage.entities import (
    FieldCandidate,
    FieldDetailCandidate,
    RequestAuthContext,
    User,
)
from stitch.entity_linkage.errors import StitchAPIError
from stitch.entity_linkage.main import app
from stitch.entity_linkage.routers import health as health_module
from stitch.entity_linkage.routers import start as start_module
from stitch.entity_linkage.auth import get_request_auth_context, get_token_claims
from stitch.entity_linkage import main as main_module


async def _noop_downstream_validate(**_: object) -> None:
    return None


def make_auth_context(
    *,
    name: str = "Integration Tester",
    email: str = "itest@example.com",
    sub: str = "auth0|itest-123",
    bearer_token: str | None = "integration-token",
) -> RequestAuthContext:
    return RequestAuthContext(
        user=User(
            id=1,
            sub=sub,
            email=email,
            name=name,
        ),
        bearer_token=bearer_token,
    )


class FakeStitchApiClient(AbstractAsyncContextManager["FakeStitchApiClient"]):
    def __init__(
        self,
        *,
        items: list[FieldCandidate] | None = None,
        pages_fetched: int = 1,
        details_by_id: dict[int, FieldDetailCandidate] | None = None,
        merge_responses_by_ids: dict[tuple[int, ...], dict] | None = None,
        auth_me_response: dict | None = None,
        collect_error: Exception | None = None,
        detail_error: Exception | None = None,
        merge_error: Exception | None = None,
        auth_me_error: Exception | None = None,
    ) -> None:
        self.items = items or []
        self.pages_fetched = pages_fetched
        self.details_by_id = details_by_id or {}
        self.merge_responses_by_ids = merge_responses_by_ids or {}
        self.auth_me_response = auth_me_response or {
            "claims": {"sub": "auth0|itest-123"}
        }
        self.collect_error = collect_error
        self.detail_error = detail_error
        self.merge_error = merge_error
        self.auth_me_error = auth_me_error

        self.collect_calls: list[dict] = []
        self.detail_calls: list[int] = []
        self.merge_calls: list[list[int]] = []
        self.auth_me_calls = 0

    async def __aenter__(self) -> "FakeStitchApiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def collect_oil_gas_fields(
        self,
        *,
        start_page: int = 1,
        page_size: int = 50,
        max_pages: int | None = None,
    ) -> tuple[list[FieldCandidate], int]:
        self.collect_calls.append(
            {
                "start_page": start_page,
                "page_size": page_size,
                "max_pages": max_pages,
            }
        )
        if self.collect_error is not None:
            raise self.collect_error
        return self.items, self.pages_fetched

    async def get_oil_gas_field_detail(self, resource_id: int) -> FieldDetailCandidate:
        self.detail_calls.append(resource_id)
        if self.detail_error is not None:
            raise self.detail_error
        return self.details_by_id[resource_id]

    async def create_merge_candidate(self, *, resource_ids: list[int]) -> dict:
        self.merge_calls.append(resource_ids)
        if self.merge_error is not None:
            raise self.merge_error
        return self.merge_responses_by_ids.get(tuple(resource_ids), {"ok": True})

    async def get_auth_me(self) -> dict:
        self.auth_me_calls += 1
        if self.auth_me_error is not None:
            raise self.auth_me_error
        return self.auth_me_response


@pytest.fixture
def auth_context() -> RequestAuthContext:
    return make_auth_context()


@pytest.fixture
def api_client_factory(
    monkeypatch: pytest.MonkeyPatch, auth_context: RequestAuthContext
):
    created_clients: list[FakeStitchApiClient] = []

    def install(
        *,
        items: list[FieldCandidate] | None = None,
        pages_fetched: int = 1,
        details_by_id: dict[int, FieldDetailCandidate] | None = None,
        merge_responses_by_ids: dict[tuple[int, ...], dict] | None = None,
        collect_error: Exception | None = None,
        detail_error: Exception | None = None,
        merge_error: Exception | None = None,
    ) -> FakeStitchApiClient:
        client = FakeStitchApiClient(
            items=items,
            pages_fetched=pages_fetched,
            details_by_id=details_by_id,
            merge_responses_by_ids=merge_responses_by_ids,
            collect_error=collect_error,
            detail_error=detail_error,
            merge_error=merge_error,
        )
        created_clients.append(client)
        monkeypatch.setattr(start_module, "StitchApiClient", lambda: client)
        return client

    return install, created_clients


@pytest.fixture
def test_client(
    auth_context: RequestAuthContext,
    monkeypatch: pytest.MonkeyPatch,
):
    async def override_auth_context() -> RequestAuthContext:
        return auth_context

    def override_token_claims() -> TokenClaims:
        return TokenClaims(
            sub=auth_context.user.sub,
            permissions=frozenset({SERVICE_ENTITY_LINKAGE_RUN}),
        )

    monkeypatch.setattr(main_module, "validate_auth_config_at_startup", lambda: None)
    monkeypatch.setattr(
        main_module, "validate_downstream_auth_at_startup", _noop_downstream_validate
    )
    app.dependency_overrides[get_request_auth_context] = override_auth_context
    app.dependency_overrides[get_token_claims] = override_token_claims

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_post_start_requires_service_permission(
    auth_context: RequestAuthContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def override_auth_context() -> RequestAuthContext:
        return auth_context

    def override_token_claims() -> TokenClaims:
        return TokenClaims(sub=auth_context.user.sub, permissions=frozenset())

    monkeypatch.setattr(main_module, "validate_auth_config_at_startup", lambda: None)
    monkeypatch.setattr(
        main_module, "validate_downstream_auth_at_startup", _noop_downstream_validate
    )
    app.dependency_overrides[get_request_auth_context] = override_auth_context
    app.dependency_overrides[get_token_claims] = override_token_claims

    with TestClient(app) as client:
        response = client.post("/api/v1/start", json={"apply_merges": False})

    app.dependency_overrides.clear()

    assert response.status_code == 403
    assert SERVICE_ENTITY_LINKAGE_RUN in response.json()["detail"]


def test_post_start_returns_serialized_response_model(
    test_client: TestClient,
    api_client_factory,
) -> None:
    install, created_clients = api_client_factory
    fake_client = install(
        items=[
            FieldCandidate(id=1, name="Alpha", country="ignored"),
            FieldCandidate(id=2, name=" alpha ", country="ignored"),
            FieldCandidate(id=3, name="Beta", country="ignored"),
        ],
        pages_fetched=2,
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Alpha", country="US"),
            2: FieldDetailCandidate(id=2, name="Alpha", country=" us "),
        },
    )

    response = test_client.post(
        "/api/v1/start",
        json={
            "apply_merges": False,
            "page": 3,
            "page_size": 25,
            "max_pages": 7,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "initiated_by": "Integration Tester",
        "apply_merges": False,
        "pages_fetched": 2,
        "total_records_fetched": 3,
        "duplicate_name_candidate_count": 2,
        "detail_records_fetched": 2,
        "match_groups": [[1, 2]],
        "merge_results": [],
    }

    assert len(created_clients) == 1
    assert fake_client.collect_calls == [
        {
            "start_page": 3,
            "page_size": 25,
            "max_pages": 7,
        }
    ]
    assert fake_client.detail_calls == [1, 2]
    assert fake_client.merge_calls == []


def test_post_start_applies_merges_and_returns_merge_results(
    test_client: TestClient,
    api_client_factory,
) -> None:
    install, _ = api_client_factory
    fake_client = install(
        items=[
            FieldCandidate(id=10, name="Alpha", country="ignored"),
            FieldCandidate(id=11, name="alpha", country="ignored"),
            FieldCandidate(id=20, name="Beta", country="ignored"),
            FieldCandidate(id=21, name="beta", country="ignored"),
        ],
        details_by_id={
            10: FieldDetailCandidate(id=10, name="Alpha", country="US"),
            11: FieldDetailCandidate(id=11, name="Alpha", country="US"),
            20: FieldDetailCandidate(id=20, name="Beta", country="CA"),
            21: FieldDetailCandidate(id=21, name="Beta", country="CA"),
        },
        merge_responses_by_ids={
            (10, 11): {"merged_ids": [10, 11], "winner": 10},
            (20, 21): {"merged_ids": [20, 21], "winner": 20},
        },
    )

    response = test_client.post(
        "/api/v1/start",
        json={"apply_merges": True},
    )

    assert response.status_code == 200
    assert response.json()["match_groups"] == [[10, 11], [20, 21]]
    assert response.json()["merge_results"] == [
        {"ids": [10, 11], "response": {"merged_ids": [10, 11], "winner": 10}},
        {"ids": [20, 21], "response": {"merged_ids": [20, 21], "winner": 20}},
    ]
    assert fake_client.merge_calls == [[10, 11], [20, 21]]


def test_post_start_returns_empty_matches_when_country_check_does_not_confirm(
    test_client: TestClient,
    api_client_factory,
) -> None:
    install, _ = api_client_factory
    install(
        items=[
            FieldCandidate(id=1, name="Alpha", country="ignored"),
            FieldCandidate(id=2, name="Alpha", country="ignored"),
            FieldCandidate(id=3, name="Gamma", country="ignored"),
        ],
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Alpha", country="US"),
            2: FieldDetailCandidate(id=2, name="Alpha", country="CA"),
        },
    )

    response = test_client.post(
        "/api/v1/start",
        json={"apply_merges": True},
    )

    assert response.status_code == 200
    assert response.json()["duplicate_name_candidate_count"] == 2
    assert response.json()["detail_records_fetched"] == 2
    assert response.json()["match_groups"] == []
    assert response.json()["merge_results"] == []


def test_post_start_translates_stitch_api_error_to_502(
    test_client: TestClient,
    api_client_factory,
) -> None:
    install, _ = api_client_factory
    install(
        collect_error=StitchAPIError(
            "GET /oil-gas-fields/ failed with status 500: boom"
        ),
    )

    response = test_client.post(
        "/api/v1/start",
        json={"apply_merges": False},
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "GET /oil-gas-fields/ failed with status 500: boom",
    }


def test_post_start_validates_request_body_constraints(
    test_client: TestClient,
    api_client_factory,
) -> None:
    install, _ = api_client_factory
    install(
        items=[],
        details_by_id={},
    )

    response = test_client.post(
        "/api/v1/start",
        json={
            "apply_merges": False,
            "page": 0,
            "page_size": 500,
            "max_pages": 0,
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]

    fields = {tuple(item["loc"]) for item in detail}
    assert ("body", "page") in fields
    assert ("body", "page_size") in fields
    assert ("body", "max_pages") in fields


def test_health_details_reports_ready_when_downstream_auth_probe_succeeds(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeStitchApiClient(
        auth_me_response={"claims": {"sub": "auth0|health-check"}}
    )
    monkeypatch.setattr(health_module, "StitchApiClient", lambda: fake_client)

    response = test_client.get("/api/v1/health/details")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["ready"] is True
    assert response.json()["downstream_api"]["ready"] is True
    assert response.json()["downstream_api"]["token_accepted"] is True
    assert response.json()["downstream_api"]["has_error"] is False
    assert response.json()["downstream_api"]["error_code"] is None
    assert fake_client.auth_me_calls == 1


def test_health_details_reports_token_not_accepted_when_downstream_is_unreachable(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeStitchApiClient(
        auth_me_error=StitchAPIError(
            "GET /auth/me failed: connection error",
            status_code=None,
            response_text=None,
        )
    )
    monkeypatch.setattr(health_module, "StitchApiClient", lambda: fake_client)

    response = test_client.get("/api/v1/health/details")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["ready"] is False
    assert response.json()["downstream_api"]["api_reachable"] is False
    assert response.json()["downstream_api"]["token_accepted"] is False
    assert response.json()["downstream_api"]["has_error"] is True
    assert response.json()["downstream_api"]["http_status"] is None
