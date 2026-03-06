"""Integration tests for resources router with real SQLite database."""

import pytest
from sqlalchemy import select

from stitch.api.db.model import ResourceModel

from tests.utils import make_empty_resource, make_create_resource


class TestResourcesIntegration:
    """Integration tests for resources endpoints with real database."""

    @pytest.mark.anyio
    async def test_get_nonexistent_returns_404(self, integration_client):
        """GET /resources/999 returns 404 status code."""
        response = await integration_client.get("/oil-gas-fields/999")

        assert response.status_code == 404
        assert "999" in response.json()["detail"]

    @pytest.mark.anyio
    async def test_create_resource_returns_resource(self, integration_client):
        """POST /resources/ returns the created resource."""
        resource_in = make_create_resource(name="Integration Test Resource")

        response = await integration_client.post(
            "/oil-gas-fields/", json=resource_in.data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Integration Test Resource"
        assert "id" in data
        assert data["id"] > 0

    @pytest.mark.anyio
    async def test_create_and_get_resource(self, integration_client):
        """POST creates resource, GET retrieves it."""
        resource_in = make_create_resource(name="Roundtrip Resource")

        create_response = await integration_client.post(
            "/oil-gas-fields/", json=resource_in.data
        )

        assert create_response.status_code == 200
        created_id = create_response.json()["id"]

        get_response = await integration_client.get(f"/oil-gas-fields/{created_id}")

        assert get_response.status_code == 200
        data = get_response.json()
        assert data["id"] == created_id
        assert data["name"] == "Roundtrip Resource"

    @pytest.mark.anyio
    async def test_create_persists_to_database(
        self, integration_client, integration_session_factory
    ):
        """POST resource is persisted and queryable directly."""
        resource_in = make_create_resource(name="Persisted Resource")

        response = await integration_client.post(
            "/oil-gas-fields/", json=resource_in.data
        )

        assert response.status_code == 200
        created_id = response.json()["id"]

        async with integration_session_factory() as session:
            result = await session.execute(
                select(ResourceModel).where(ResourceModel.id == created_id)
            )
            resource = result.scalar_one_or_none()

        assert resource is not None
        assert resource.name == "Persisted Resource"

    @pytest.mark.anyio
    async def test_create_with_minimal_data(self, integration_client):
        """POST /resources/ works with only required fields (no source data)."""
        resource_in = make_empty_resource(name=None)

        response = await integration_client.post(
            "/oil-gas-fields/", json=resource_in.data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] > 0
        assert data["name"] is None
