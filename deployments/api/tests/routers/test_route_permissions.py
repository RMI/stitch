from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from stitch.auth import TokenClaims
from stitch.auth.permissions import (
    MERGE_CANDIDATE_CREATE,
    MERGE_CANDIDATE_READ,
    MERGE_CANDIDATE_REVIEW,
    RESOURCE_READ,
    RESOURCE_WRITE,
    SOURCE_READ_GEM,
    SOURCE_WRITE,
)

from stitch.api.auth import get_token_claims
from stitch.api.db.config import get_uow
from stitch.api.main import app


def _claims(*permissions: str) -> TokenClaims:
    return TokenClaims(sub="test|user-1", permissions=frozenset(permissions))


def _uow_override(mock_uow):
    async def override_uow():
        yield mock_uow

    return override_uow


def _source_payload() -> dict:
    return {
        "source": "gem",
        "name": "Alpha",
        "country": "USA",
        "source_record": {
            "observed_at": "2026-01-01T00:00:00Z",
            "producer": "test",
            "payload": {},
        },
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "permissions", "missing_permission", "json_body"),
    [
        ("get", "/oil-gas-fields/", (), RESOURCE_READ, None),
        (
            "post",
            "/oil-gas-fields/",
            (RESOURCE_READ,),
            RESOURCE_WRITE,
            {"source_data": []},
        ),
        (
            "get",
            "/oil-gas-fields/merge-candidates",
            (RESOURCE_READ,),
            MERGE_CANDIDATE_READ,
            None,
        ),
        (
            "post",
            "/oil-gas-fields/merge-candidates",
            (MERGE_CANDIDATE_READ,),
            MERGE_CANDIDATE_CREATE,
            {"resource_ids": [1, 2]},
        ),
        (
            "post",
            "/oil-gas-fields/merge-candidates/1/approve",
            (MERGE_CANDIDATE_READ,),
            MERGE_CANDIDATE_REVIEW,
            {},
        ),
        (
            "post",
            "/oil-gas-field-sources/",
            (SOURCE_READ_GEM,),
            SOURCE_WRITE,
            _source_payload(),
        ),
        (
            "put",
            "/oil-gas-fields/1/fields/basin/sources/priority",
            (RESOURCE_READ,),
            RESOURCE_WRITE,
            {"ordered_source_pks": [1, 2]},
        ),
    ],
)
async def test_route_returns_403_when_required_permission_missing(
    async_client: AsyncClient,
    mock_uow,
    method: str,
    path: str,
    permissions: tuple[str, ...],
    missing_permission: str,
    json_body: dict | None,
):
    app.dependency_overrides[get_token_claims] = lambda: _claims(*permissions)
    app.dependency_overrides[get_uow] = _uow_override(mock_uow)

    response = await async_client.request(method, path, json=json_body)

    assert response.status_code == 403
    assert missing_permission in response.json()["detail"]


@pytest.mark.anyio
async def test_merge_candidate_read_permission_allows_list_route(
    async_client: AsyncClient,
    mock_uow,
):
    app.dependency_overrides[get_token_claims] = lambda: _claims(MERGE_CANDIDATE_READ)
    app.dependency_overrides[get_uow] = _uow_override(mock_uow)

    with patch("stitch.api.routers.oil_gas_fields.merge_candidate_actions") as actions:
        actions.list_merge_candidates = AsyncMock(return_value=[])
        response = await async_client.get("/oil-gas-fields/merge-candidates")

    assert response.status_code == 200
    assert response.json() == []
