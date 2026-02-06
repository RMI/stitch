"""Integration tests for resources router with real SQLite database."""

import pytest
from sqlalchemy import select

from stitch.api.db.model import ResourceModel

from tests.utils import (
    make_empty_resource,
    make_gem_data,
    make_resource_with_new_sources,
    make_wm_data,
)


class TestResourcesIntegration:
    """Integration tests for resources endpoints with real database."""

    @pytest.mark.anyio
    async def test_get_nonexistent_returns_404(self, integration_client):
        """GET /resources/999 returns 404 status code."""
        response = await integration_client.get("/resources/999")

        assert response.status_code == 404
        assert "999" in response.json()["detail"]

    @pytest.mark.anyio
    async def test_create_resource_returns_resource(self, integration_client):
        """POST /resources/ returns the created resource."""
        resource_in = make_resource_with_new_sources(
            gem=make_gem_data(
                name="GEM Integration Field", latitude=40.0, longitude=-100.0
            ).model,
            name="Integration Test Resource",
            country="USA",
        )

        response = await integration_client.post("/resources/", json=resource_in.data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Integration Test Resource"
        assert data["country"] == "USA"
        assert "id" in data
        assert data["id"] > 0

    @pytest.mark.anyio
    async def test_create_and_get_resource(self, integration_client):
        """POST creates resource, GET retrieves it."""
        resource_in = make_resource_with_new_sources(
            wm=make_wm_data(name="WM Roundtrip Field", country="CAN").model,
            name="Roundtrip Resource",
            country="CAN",
        )

        create_response = await integration_client.post(
            "/resources/", json=resource_in.data
        )

        assert create_response.status_code == 200
        created_id = create_response.json()["id"]

        get_response = await integration_client.get(f"/resources/{created_id}")

        assert get_response.status_code == 200
        data = get_response.json()
        assert data["id"] == created_id
        assert data["name"] == "Roundtrip Resource"
        assert data["country"] == "CAN"

    @pytest.mark.anyio
    async def test_create_persists_to_database(
        self, integration_client, integration_session_factory
    ):
        """POST resource is persisted and queryable directly."""
        resource_in = make_resource_with_new_sources(
            gem=make_gem_data(
                name="GEM Persist Field", latitude=25.0, longitude=-105.0, country="MEX"
            ).model,
            name="Persisted Resource",
            country="MEX",
        )

        response = await integration_client.post("/resources/", json=resource_in.data)

        assert response.status_code == 200
        created_id = response.json()["id"]

        async with integration_session_factory() as session:
            result = await session.execute(
                select(ResourceModel).where(ResourceModel.id == created_id)
            )
            resource = result.scalar_one_or_none()

        assert resource is not None
        assert resource.name == "Persisted Resource"
        assert resource.country == "MEX"

    @pytest.mark.anyio
    async def test_create_with_minimal_data(self, integration_client):
        """POST /resources/ works with only required fields (no source data)."""
        resource_in = make_empty_resource(name=None, country=None)

        response = await integration_client.post("/resources/", json=resource_in.data)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] > 0
        assert data["name"] is None
        assert data["country"] is None
