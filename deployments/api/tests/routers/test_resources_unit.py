"""Unit tests for resources router with mocked dependencies."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.status import HTTP_404_NOT_FOUND

from stitch.api.db.config import get_uow
from stitch.api.entities import Resource, SourceData
from stitch.api.main import app

from tests.utils import (
    make_gem_data,
    make_resource_with_new_sources,
    make_wm_data,
)


def make_resource(
    id: int = 1,
    name: str = "Test Resource",
    country: str = "USA",
) -> Resource:
    """Factory for creating Resource entities for tests."""
    now = datetime.now(timezone.utc)
    return Resource(
        id=id,
        name=name,
        country=country,
        source_data=SourceData(),
        constituents=[],
        created=now,
        updated=now,
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

        with patch("stitch.api.routers.resources.resource_actions") as mock_repo:
            mock_repo.get = AsyncMock(return_value=expected)

            response = await async_client.get("/resources/42")

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

        with patch("stitch.api.routers.resources.resource_actions") as mock_repo:
            mock_repo.get = AsyncMock(
                side_effect=HTTPException(
                    status_code=HTTP_404_NOT_FOUND,
                    detail="No Resource with id `999` found.",
                )
            )

            response = await async_client.get("/resources/999")

        assert response.status_code == 404
        assert "999" in response.json()["detail"]


class TestCreateResourceUnit:
    """Unit tests for POST /resources/ endpoint."""

    @pytest.mark.anyio
    async def test_creates_resource_with_user(self, async_client, mock_uow, test_user):
        """POST /resources/ calls repo.create with user and data."""
        expected = make_resource(id=123, name="New Resource", country="CAN")
        resource_in = make_resource_with_new_sources(
            gem=make_gem_data(
                name="GEM Field", lat=45.0, lon=-120.0, country="CAN"
            ).model,
            name="New Resource",
            country="CAN",
        )

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.resources.resource_actions") as mock_repo:
            mock_repo.create = AsyncMock(return_value=expected)

            response = await async_client.post("/resources/", json=resource_in.data)

        assert response.status_code == 200
        mock_repo.create.assert_awaited_once()
        call_kwargs = mock_repo.create.call_args.kwargs
        assert call_kwargs["user"].id == test_user.id

    @pytest.mark.anyio
    async def test_returns_created_resource(self, async_client, mock_uow):
        """POST /resources/ returns the created resource entity."""
        expected = make_resource(id=456, name="Created Resource")
        resource_in = make_resource_with_new_sources(
            wm=make_wm_data(
                field_name="WM Field", field_country="USA", production=1000.0
            ).model,
            name="Created Resource",
        )

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.resources.resource_actions") as mock_repo:
            mock_repo.create = AsyncMock(return_value=expected)

            response = await async_client.post("/resources/", json=resource_in.data)

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

        response = await async_client.post(
            "/resources/",
            json={
                "name": "Test Resource",
                "source_data": {
                    "gem": [{"invalid_field": "bad"}],
                },
            },
        )

        assert response.status_code == 422
