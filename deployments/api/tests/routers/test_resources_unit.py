"""Unit tests for resources router with mocked dependencies."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.status import HTTP_404_NOT_FOUND
from stitch.ogsi.model import OGFieldListItemView, OilGasFieldBase

from stitch.api.db.config import get_uow
from stitch.api.main import app

from tests.factories import ResourceCreateFactory, SourceFactory


class TestGetResourceUnit:
    """Unit tests for GET /resources/{id} endpoint."""

    @pytest.mark.anyio
    async def test_returns_resource_when_found(
        self,
        async_client,
        mock_uow,
        og_res_fact: ResourceCreateFactory,
        source_maker: SourceFactory,
    ):
        """GET /resources/{id} returns resource from repository."""
        expected = og_res_fact(
            id=42,
            empty=False,
            view=OilGasFieldBase(name="Found Resource", country="USA"),
        )

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.get = AsyncMock(return_value=expected)

            response = await async_client.get("/oil-gas-fields/42")

        assert response.status_code == 200
        view_data = response.json()
        assert view_data["id"] == 42
        assert view_data["name"] == "Found Resource"

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
    async def test_creates_resource_with_user(
        self,
        async_client,
        mock_uow,
        test_user,
        og_res_fact: ResourceCreateFactory,
        og_create_res_fact: ResourceCreateFactory,
        source_maker: SourceFactory,
    ):
        """POST /resources/ calls repo.create with user and data."""
        src = source_maker(id=1, source="wm")
        expected = og_res_fact(id=123, source_data=[src])
        resource_in = og_create_res_fact(sources=["wm"])

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.create = AsyncMock(return_value=expected)

            response = await async_client.post(
                "/oil-gas-fields/", json=resource_in.model_dump(mode="json")
            )

        assert response.status_code == 200
        mock_repo.create.assert_awaited_once()
        call_kwargs = mock_repo.create.call_args.kwargs
        assert call_kwargs["user"].id == test_user.id
        assert call_kwargs["resource"].id is None
        assert len(call_kwargs["resource"].source_data) == 1

    @pytest.mark.anyio
    async def test_returns_created_resource(
        self,
        async_client,
        mock_uow,
        og_res_fact: ResourceCreateFactory,
        og_create_res_fact: ResourceCreateFactory,
        source_maker: SourceFactory,
    ):
        """POST /resources/ returns the created resource entity."""
        src = source_maker(id=1, source="wm", name="Created Resource")
        expected = og_res_fact(id=456, source_data=[src])
        resource_in = og_create_res_fact(name="Created Resource", sources=[])

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.create = AsyncMock(return_value=expected)

            response = await async_client.post(
                "/oil-gas-fields/", json=resource_in.model_dump(mode="json")
            )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 456
        assert len((source_data := data.get("source_data", []))) == 1
        assert source_data[0]["name"] == "Created Resource"

    @pytest.mark.anyio
    async def test_validates_request_body(self, async_client, mock_uow):
        """POST /resources/ returns 422 for invalid request body with bad source_data."""

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        response = await async_client.post("/oil-gas-fields/", json={"label": 123})

        assert response.status_code == 422


class TestGetAllResourcesUnit:
    """Unit tests for GET /oil-gas-fields/ paginated endpoint."""

    @pytest.mark.anyio
    async def test_returns_paginated_response(
        self,
        async_client,
        mock_uow,
    ):
        """GET /oil-gas-fields/ returns envelope with items and metadata."""
        list_items = [
            OGFieldListItemView(
                id=i,
                data=OilGasFieldBase(name=f"R{i}", country=None),
                provenance={"name": "rmi"},
            )
            for i in range(10, 13)
        ]

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.query = AsyncMock(return_value=(list_items, 3))

            response = await async_client.get("/oil-gas-fields/")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 3
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert len(data["items"]) == 3

    @pytest.mark.anyio
    async def test_passes_pagination_params(
        self,
        async_client,
        mock_uow,
    ):
        """GET /oil-gas-fields/?page=2&page_size=10 passes params to query."""

        async def override_get_uow():
            yield mock_uow

        app.dependency_overrides[get_uow] = override_get_uow

        with patch("stitch.api.routers.oil_gas_fields.resource_actions") as mock_repo:
            mock_repo.query = AsyncMock(return_value=([], 0))

            response = await async_client.get("/oil-gas-fields/?page=2&page_size=10")

        assert response.status_code == 200
        mock_repo.query.assert_awaited_once()
        call_kwargs = mock_repo.query.call_args.kwargs
        params = call_kwargs["params"]
        assert params.offset == 10
        assert params.limit == 10
