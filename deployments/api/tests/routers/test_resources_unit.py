"""Unit tests for resources router with mocked dependencies."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.status import HTTP_404_NOT_FOUND

from stitch.api.db.config import get_uow
from stitch.api.main import app

from tests.utils import make_create_resource

from stitch.api.entities import Resource


def make_resource(
    id: int = 1,
    name: str | None = "Test Resource",
) -> Resource:
    """Factory for creating Resource entities for tests."""
    return Resource(
        id=id,
        name=name,
    )


class TestGetResourceUnit:
    """Unit tests for GET /resources/{id} endpoint."""

    @pytest.mark.anyio
    async def test_returns_resource_when_found(self, async_client, mock_uow):
        """GET /resources/{id} returns resource from repository."""
        expected = make_resource(id=42, name="Found Resource")

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.get = AsyncMock(return_value=expected)

            response = await async_client.get("/oil-gas-fields/42")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 42
        assert data["name"] == "Found Resource"

    @pytest.mark.anyio
    async def test_returns_404_when_not_found(self, async_client, mock_uow):
        """GET /resources/{id} returns 404 when resource not found."""

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.get = AsyncMock(
                side_effect=HTTPException(
                    status_code=HTTP_404_NOT_FOUND,
                    detail="No Resource with id `999` found.",
                )
            )

            response = await async_client.get("/oil-gas-fields/999")

        assert response.status_code == 404
        assert "999" in response.json()["detail"]


class TestCreateResourceUnit:
    """Unit tests for POST /resources/ endpoint."""

    @pytest.mark.anyio
    async def test_creates_resource_with_user(self, async_client, mock_uow, test_user):
        """POST /resources/ calls repo.create with user and data."""
        expected = make_resource(id=123, name="New Resource")
        resource_in = make_create_resource(name="New Resource")

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.create = AsyncMock(return_value=expected)

            response = await async_client.post("/oil-gas-fields/", json=resource_in.data)

        assert response.status_code == 200
        mock_repo.create.assert_awaited_once()
        call_kwargs = mock_repo.create.call_args.kwargs
        assert call_kwargs["user"].id == test_user.id

    @pytest.mark.anyio
    async def test_returns_created_resource(self, async_client, mock_uow):
        """POST /resources/ returns the created resource entity."""
        expected = make_resource(id=456, name="Created Resource")
        resource_in = make_create_resource(name="Created Resource")

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.create = AsyncMock(return_value=expected)

            response = await async_client.post("/oil-gas-fields/", json=resource_in.data)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 456
        assert data["name"] == "Created Resource"

    @pytest.mark.anyio
    async def test_validates_request_body(self, async_client, mock_uow):
        """POST /resources/ returns 422 for invalid request body with bad source_data."""

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        response = await async_client.post("/oil-gas-fields/", json={"label": 123})

        assert response.status_code == 422
