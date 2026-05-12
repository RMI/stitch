"""Unit tests for oil-gas-field-sources router."""

from unittest.mock import AsyncMock, patch

import pytest
from tests.utils import make_source_record

from stitch.api.db.config import get_uow
from stitch.api.main import app


class TestQuerySourcesUnit:
    """Unit tests for GET /oil-gas-field-sources/ paginated endpoint."""

    @pytest.mark.anyio
    async def test_returns_paginated_response(self, async_client, mock_uow):
        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch(
            "stitch.api.routers.oil_gas_field_sources.og_field_source_actions"
        ) as mock_repo:
            mock_repo.query = AsyncMock(return_value=([], 0))

            response = await async_client.get("/oil-gas-field-sources/")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert data["total_count"] == 0
        assert data["items"] == []


class TestCreateSourceUnit:
    @pytest.mark.anyio
    async def test_rejects_missing_source_record(self, async_client, mock_uow):
        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        response = await async_client.post(
            "/oil-gas-field-sources/",
            json={"source": "gem", "name": "Alpha", "country": "USA"},
        )

        assert response.status_code == 422


class TestGetSourceDetailUnit:
    @pytest.mark.anyio
    async def test_returns_detail_with_source_record(self, async_client, mock_uow):
        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch(
            "stitch.api.routers.oil_gas_field_sources.og_field_source_actions"
        ) as mock_repo:
            mock_repo.get_source_detail = AsyncMock(
                return_value={
                    "id": 7,
                    "source": "gem",
                    "name": "Alpha",
                    "country": "USA",
                    "source_record": make_source_record(
                        payload={"source": "gem", "name": "Alpha"}
                    ),
                    "source_record_hash": "hash-1",
                }
            )

            response = await async_client.get("/oil-gas-field-sources/7/detail")

        assert response.status_code == 200
        data = response.json()
        assert data["source_record"]["producer"] == "stitch-seed@test"
        assert data["source_record_hash"] == "hash-1"
