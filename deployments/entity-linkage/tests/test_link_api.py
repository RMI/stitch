from __future__ import annotations

import time
from contextlib import AbstractAsyncContextManager

import pytest
from fastapi.testclient import TestClient

import stitch.entity_linkage.main as main_module
from stitch.auth import TokenClaims
from stitch.auth.permissions import SERVICE_ENTITY_LINKAGE_RUN
from stitch.entity_linkage.auth import get_request_auth_context, get_token_claims
from stitch.entity_linkage.entities import (
    FieldCandidate,
    FieldDetailCandidate,
    RequestAuthContext,
    User,
)
from stitch.entity_linkage.errors import StitchAPIError
from stitch.entity_linkage.jobs import reset_manager
from stitch.entity_linkage.main import app
from stitch.entity_linkage.routers import link as link_module

STATUS_URL = "/api/v1/oil-gas-fields/link/status"


@pytest.fixture(autouse=True)
def _reset_job_manager():
    reset_manager()
    yield
    reset_manager()


def make_auth_context() -> RequestAuthContext:
    return RequestAuthContext(
        user=User(
            id=1,
            sub="auth0|itest-123",
            email="itest@example.com",
            name="Integration Tester",
        ),
        bearer_token="integration-token",
    )


class FakeStitchApiClient(AbstractAsyncContextManager["FakeStitchApiClient"]):
    def __init__(
        self,
        *,
        items: list[FieldCandidate] | None = None,
        details_by_id: dict[int, FieldDetailCandidate] | None = None,
        existing_candidates: list[dict] | None = None,
        detail_error: Exception | None = None,
        list_error: Exception | None = None,
    ) -> None:
        self.items = items or []
        self.details_by_id = details_by_id or {}
        self.existing_candidates = existing_candidates or []
        self.detail_error = detail_error
        self.list_error = list_error
        self.create_calls: list[list[int]] = []

    async def __aenter__(self) -> "FakeStitchApiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get_oil_gas_field_detail(self, resource_id: int) -> FieldDetailCandidate:
        if self.detail_error is not None:
            raise self.detail_error
        return self.details_by_id[resource_id]

    async def collect_oil_gas_fields(
        self,
        *,
        start_page: int = 1,
        page_size: int = 50,
        max_pages: int | None = None,
        q: str | None = None,
        name: str | None = None,
        country: str | None = None,
    ) -> tuple[list[FieldCandidate], int]:
        superset = [
            item
            for item in self.items
            if q is None
            or (item.name is not None and q.casefold() in item.name.casefold())
        ]
        return superset, 1

    async def iter_oil_gas_fields(
        self,
        *,
        start_page: int = 1,
        page_size: int = 50,
        max_pages: int | None = None,
        q: str | None = None,
        name: str | None = None,
        country: str | None = None,
    ):
        for item in self.items:
            yield item

    async def create_merge_candidate(self, *, resource_ids: list[int]) -> dict:
        self.create_calls.append(list(resource_ids))
        return {"ok": True, "resource_ids": list(resource_ids)}

    async def list_merge_candidates(self) -> list[dict]:
        if self.list_error is not None:
            raise self.list_error
        return self.existing_candidates


@pytest.fixture
def install_client(monkeypatch: pytest.MonkeyPatch):
    def install(**kwargs) -> FakeStitchApiClient:
        client = FakeStitchApiClient(**kwargs)
        monkeypatch.setattr(link_module, "StitchApiClient", lambda: client)
        return client

    return install


@pytest.fixture
def test_client(monkeypatch: pytest.MonkeyPatch):
    auth_context = make_auth_context()

    async def override_auth_context() -> RequestAuthContext:
        return auth_context

    def override_token_claims() -> TokenClaims:
        return TokenClaims(
            sub=auth_context.user.sub,
            permissions=frozenset({SERVICE_ENTITY_LINKAGE_RUN}),
        )

    monkeypatch.setattr(main_module, "validate_auth_config_at_startup", lambda: None)
    monkeypatch.setattr(
        main_module, "validate_downstream_auth_config_at_startup", lambda: None
    )
    app.dependency_overrides[get_request_auth_context] = override_auth_context
    app.dependency_overrides[get_token_claims] = override_token_claims

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_link_one_requires_service_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    auth_context = make_auth_context()

    async def override_auth_context() -> RequestAuthContext:
        return auth_context

    def override_token_claims() -> TokenClaims:
        return TokenClaims(sub=auth_context.user.sub, permissions=frozenset())

    monkeypatch.setattr(main_module, "validate_auth_config_at_startup", lambda: None)
    monkeypatch.setattr(
        main_module, "validate_downstream_auth_config_at_startup", lambda: None
    )
    app.dependency_overrides[get_request_auth_context] = override_auth_context
    app.dependency_overrides[get_token_claims] = override_token_claims

    with TestClient(app) as client:
        response = client.post("/api/v1/oil-gas-fields/1/link", json={})

    app.dependency_overrides.clear()

    assert response.status_code == 403
    assert SERVICE_ENTITY_LINKAGE_RUN in response.json()["detail"]


def test_link_one_dry_run_returns_match_group(test_client, install_client) -> None:
    install_client(
        items=[
            FieldCandidate(id=1, name="Alpha", country="US"),
            FieldCandidate(id=2, name="alpha", country="US"),
        ],
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Alpha", country="US"),
            2: FieldDetailCandidate(id=2, name="alpha", country="US"),
        },
    )

    response = test_client.post("/api/v1/oil-gas-fields/1/link", json={})

    assert response.status_code == 200
    assert response.json() == {
        "resource_id": 1,
        "matched_ids": [1, 2],
        "merge_candidate_created": False,
        "skipped_existing": False,
    }


def test_link_one_applies_merge(test_client, install_client) -> None:
    fake = install_client(
        items=[
            FieldCandidate(id=1, name="Alpha", country="US"),
            FieldCandidate(id=2, name="alpha", country="US"),
        ],
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Alpha", country="US"),
            2: FieldDetailCandidate(id=2, name="alpha", country="US"),
        },
    )

    response = test_client.post(
        "/api/v1/oil-gas-fields/1/link", json={"apply_merges": True}
    )

    assert response.status_code == 200
    assert response.json()["merge_candidate_created"] is True
    assert fake.create_calls == [[1, 2]]


def test_link_one_translates_stitch_api_error_to_502(
    test_client, install_client
) -> None:
    install_client(
        detail_error=StitchAPIError(
            "GET /oil-gas-fields/1/detail failed with status 500: boom",
            status_code=500,
        ),
    )

    response = test_client.post("/api/v1/oil-gas-fields/1/link", json={})

    assert response.status_code == 502
    assert response.json() == {
        "detail": "GET /oil-gas-fields/1/detail failed with status 500: boom",
    }


def _poll_status(client: TestClient, *, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(STATUS_URL).json()
        if body["state"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError("linkage job did not finish within timeout")


def test_link_all_launches_job_and_status_succeeds(test_client, install_client) -> None:
    fake = install_client(
        items=[
            FieldCandidate(id=1, name="Alpha", country="US"),
            FieldCandidate(id=2, name="alpha", country="US"),
            FieldCandidate(id=3, name="Beta", country="CA"),
        ],
        details_by_id={
            1: FieldDetailCandidate(id=1, name="Alpha", country="US"),
            2: FieldDetailCandidate(id=2, name="alpha", country="US"),
            3: FieldDetailCandidate(id=3, name="Beta", country="CA"),
        },
    )

    response = test_client.post(
        "/api/v1/oil-gas-fields/link", json={"apply_merges": True}
    )

    assert response.status_code == 202
    start_body = response.json()
    assert start_body["state"] == "running"
    assert start_body["initiated_by"] == "Integration Tester"
    job_id = start_body["job_id"]

    final = _poll_status(test_client)
    assert final["job_id"] == job_id
    assert final["state"] == "succeeded"
    assert final["error"] is None
    assert final["finished_at"] is not None
    result = final["result"]
    assert result["resources_scanned"] == 3
    assert result["match_groups"] == [[1, 2]]
    assert result["merge_candidates_created"] == 1
    assert result["merge_candidates_skipped"] == 0
    assert fake.create_calls == [[1, 2]]


def test_link_all_records_downstream_failure_in_status(
    test_client, install_client
) -> None:
    install_client(
        list_error=StitchAPIError(
            "GET /oil-gas-fields/merge-candidates failed with status 500: boom",
            status_code=500,
        ),
    )

    # apply_merges so the run fetches the candidate queue (skipped on dry runs)
    # and surfaces the downstream error.
    response = test_client.post(
        "/api/v1/oil-gas-fields/link", json={"apply_merges": True}
    )
    assert response.status_code == 202

    final = _poll_status(test_client)
    assert final["state"] == "failed"
    assert "boom" in final["error"]
    assert final["result"] is None


def test_link_all_rejects_concurrent_run_with_409(
    test_client, install_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_client()

    async def slow_link_all(client, *, apply_merges, page_size, initiated_by):
        import asyncio

        await asyncio.sleep(0.5)
        from stitch.entity_linkage.entities import BulkLinkResponse

        return BulkLinkResponse(
            initiated_by=initiated_by,
            apply_merges=apply_merges,
            resources_scanned=0,
            match_groups=[],
            merge_candidates_created=0,
            merge_candidates_skipped=0,
        )

    monkeypatch.setattr(link_module.matching, "link_all", slow_link_all)

    first = test_client.post("/api/v1/oil-gas-fields/link", json={})
    assert first.status_code == 202

    second = test_client.post("/api/v1/oil-gas-fields/link", json={})
    assert second.status_code == 409
    assert first.json()["job_id"] in second.json()["detail"]

    _poll_status(test_client)


def test_link_all_status_returns_404_when_no_run_started(test_client) -> None:
    assert test_client.get(STATUS_URL).status_code == 404
