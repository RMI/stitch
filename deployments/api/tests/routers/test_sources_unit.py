"""Unit tests for oil-gas-field-sources router."""

from unittest.mock import AsyncMock, patch

import pytest
from stitch.ogsi.model import GemSource

from stitch.api.db.errors import SourceNotFoundError
from tests.utils import make_source_record


class TestQuerySourcesUnit:
    """Unit tests for GET /oil-gas-field-sources/ paginated endpoint."""

    @pytest.mark.anyio
    async def test_returns_paginated_response(self, client, mock_uow):
        with patch(
            "stitch.api.routers.oil_gas_field_sources.og_field_source_actions"
        ) as mock_repo:
            mock_repo.query = AsyncMock(return_value=([], 0))

            response = await client.get("/oil-gas-field-sources/")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert data["total_count"] == 0
        assert data["items"] == []


class TestSourceDetailUnit:
    @pytest.mark.anyio
    async def test_get_detail_returns_source_record(self, client, mock_uow):
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

            response = await client.get("/oil-gas-field-sources/1/detail")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "gem"
        assert data["source_record"]["producer"] == "test-producer"

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        ("path", "action"),
        [
            ("/oil-gas-field-sources/1", "get_source"),
            ("/oil-gas-field-sources/1/detail", "get_source_detail"),
        ],
    )
    async def test_hidden_or_missing_source_returns_404(
        self, client, mock_uow, path, action
    ):
        with patch(
            "stitch.api.routers.oil_gas_field_sources.og_field_source_actions"
        ) as mock_repo:
            setattr(mock_repo, action, AsyncMock(side_effect=SourceNotFoundError("x")))

            response = await client.get(path)

        assert response.status_code == 404


class TestCreateSourceUnit:
    @pytest.mark.anyio
    async def test_create_rejects_missing_source_record(self, client, mock_uow):
        response = await client.post(
            "/oil-gas-field-sources/",
            json={
                "source": "gem",
                "name": "Alpha",
                "country": "USA",
            },
        )

        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(error["loc"][-1] == "source_record" for error in errors)
