"""Unit tests for oil-gas-field-sources router."""

from unittest.mock import AsyncMock, patch

import pytest
from stitch.ogsi.model import GemSource

from stitch.api.db.config import get_uow
from stitch.api.main import app
from tests.utils import make_source_record


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


class TestSourceDetailUnit:
    @pytest.mark.anyio
    async def test_get_detail_returns_source_record(self, async_client, mock_uow):
        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        source = GemSource(
            id=1,
            name="Alpha",
            country="USA",
            source_record=make_source_record({"source": "gem", "name": "Alpha"}),
        )

        with patch(
            "stitch.api.routers.oil_gas_field_sources.og_field_source_actions"
        ) as mock_repo:
            mock_repo.get_source_detail = AsyncMock(return_value=source)

            response = await async_client.get("/oil-gas-field-sources/1/detail")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "gem"
        assert data["source_record"]["producer"] == "test-producer"
