"""Unit tests for query param validation on list endpoints."""

import pytest
from httpx import AsyncClient

from stitch.api.entities import OGFieldQueryParams, OGSI_SOURCE_DEFAULT


class TestOGFieldQueryParams:
    """Verify shared query-param model behavior."""

    def test_source_defaults_to_all_ogsi_sources(self):
        params = OGFieldQueryParams()

        assert params.source == list(OGSI_SOURCE_DEFAULT)

    def test_explicit_source_list_is_preserved(self):
        params = OGFieldQueryParams(source=["gem", "wm"])

        assert params.source == ["gem", "wm"]


class TestResourceRouterParamValidation:
    """Verify FastAPI/Pydantic rejects invalid filter/sort params on GET /oil-gas-fields/."""

    @pytest.mark.anyio
    async def test_invalid_field_status_returns_422(self, async_client: AsyncClient):
        """field_status must be a valid FieldStatus literal."""
        resp = await async_client.get(
            "/oil-gas-fields/", params={"field_status": "BadValue"}
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_invalid_sort_by_returns_422(self, async_client: AsyncClient):
        """sort_by must be one of the SortableField values."""
        resp = await async_client.get("/oil-gas-fields/", params={"sort_by": "owners"})
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_invalid_sort_order_returns_422(self, async_client: AsyncClient):
        """sort_order must be 'asc' or 'desc'."""
        resp = await async_client.get(
            "/oil-gas-fields/", params={"sort_order": "sideways"}
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_invalid_location_type_returns_422(self, async_client: AsyncClient):
        """location_type must be a valid LocationType literal."""
        resp = await async_client.get(
            "/oil-gas-fields/", params={"location_type": "Underground"}
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_sort_by_source_returns_422(self, integration_client: AsyncClient):
        """Resource list does not support source-table ordering."""
        resp = await integration_client.get(
            "/oil-gas-fields/", params={"sort_by": "source"}
        )
        assert resp.status_code == 422


class TestSourceRouterParamValidation:
    """Verify FastAPI/Pydantic rejects invalid filter/sort params on GET /oil-gas-field-sources/."""

    @pytest.mark.anyio
    async def test_invalid_field_status_returns_422(self, async_client: AsyncClient):
        """field_status must be a valid FieldStatus literal."""
        resp = await async_client.get(
            "/oil-gas-field-sources/", params={"field_status": "BadValue"}
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_invalid_sort_by_returns_422(self, async_client: AsyncClient):
        """sort_by must be one of the SortableField values."""
        resp = await async_client.get(
            "/oil-gas-field-sources/", params={"sort_by": "owners"}
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_invalid_sort_order_returns_422(self, async_client: AsyncClient):
        """sort_order must be 'asc' or 'desc'."""
        resp = await async_client.get(
            "/oil-gas-field-sources/", params={"sort_order": "sideways"}
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_invalid_source_returns_422(self, async_client: AsyncClient):
        """source must be a valid OGSISrcKey literal."""
        resp = await async_client.get(
            "/oil-gas-field-sources/", params={"source": "not_a_source"}
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_sort_by_source_is_allowed_for_sources(
        self, integration_client: AsyncClient
    ):
        """Direct source-table query keeps source ordering available."""
        resp = await integration_client.get(
            "/oil-gas-field-sources/", params={"sort_by": "source"}
        )
        assert resp.status_code == 200
