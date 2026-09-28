"""Integration tests for resources router with real SQLite database."""

from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.factories import ResourceCreateFactory, SourceFactory
from stitch.api.db.model import ResourceModel


class TestResourcesIntegration:
    """Integration tests for resources endpoints with real database."""

    @pytest.mark.anyio
    async def test_get_nonexistent_returns_404(self, integration_client):
        """GET /resources/999 returns 404 status code."""
        response = await integration_client.get("/oil-gas-fields/999")

        assert response.status_code == 404
        assert "999" in response.json()["detail"]

    @pytest.mark.anyio
    async def test_create_resource_returns_resource(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        """POST /resources/ returns the created resource."""
        resource_in = og_create_res_fact(name="Integration Test Resource")

        response = await integration_client.post(
            "/oil-gas-fields/", json=resource_in.model_dump(mode="json")
        )

        assert response.status_code == 200
        data = response.json()
        assert data["view"]["name"] == "Integration Test Resource"
        assert "id" in data
        assert data["id"] > 0

    @pytest.mark.anyio
    async def test_create_and_get_resource(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        """POST creates resource, GET retrieves it."""
        resource_in = og_create_res_fact(name="Roundtrip Resource")

        create_response = await integration_client.post(
            "/oil-gas-fields/", json=resource_in.model_dump(mode="json")
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
        self,
        integration_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        og_create_res_fact: ResourceCreateFactory,
    ):
        """POST resource is persisted and queryable directly."""
        resource_in = og_create_res_fact(name="Persisted Resource")

        response = await integration_client.post(
            "/oil-gas-fields/", json=resource_in.model_dump(mode="json")
        )

        assert response.status_code == 200
        created_id = response.json()["id"]

        async with integration_session_factory() as session:
            result = await session.execute(
                select(ResourceModel).where(ResourceModel.id == created_id)
            )
            resource = result.scalar_one_or_none()
            assert resource is not None
            assert resource.id is not None

            sources = await resource.get_source_data(session)

        assert len(sources) > 0
        rmi_sources = [src for src in sources if src.source == "rmi"]
        assert len(rmi_sources) == 1
        assert rmi_sources[0].name == "Persisted Resource"

    @pytest.mark.anyio
    async def test_create_with_minimal_data(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
        source_maker: SourceFactory,
    ):
        """POST /resources/ works with only required fields (no source data)."""
        resource_in = og_create_res_fact(name="Minimal Name", sources=[])

        response = await integration_client.post(
            "/oil-gas-fields/", json=resource_in.model_dump(mode="json")
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] > 0
        assert (view := data.get("view", None)) is not None
        assert view["name"] == "Minimal Name"


class TestRepointedResourceRedirect:
    """GET on a merged-away resource resolves to its terminal resource (STIT-418)."""

    async def _create(self, client: AsyncClient, fact, name: str) -> int:
        resp = await client.post(
            "/oil-gas-fields/", json=fact(name=name).model_dump(mode="json")
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["id"]

    async def _repoint(self, session_factory, old_id: int, new_id: int) -> None:
        """Point old_id at new_id, mirroring what apply_resource_merge does to a row."""
        async with session_factory() as session:
            model = await session.get(ResourceModel, old_id)
            model.repointed_id = new_id
            await session.commit()

    @pytest.mark.anyio
    async def test_detail_resolves_to_root_with_flag(
        self,
        integration_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        og_create_res_fact: ResourceCreateFactory,
    ):
        root_id = await self._create(
            integration_client, og_create_res_fact, "Merged Root"
        )
        old_id = await self._create(integration_client, og_create_res_fact, "Old Shell")
        await self._repoint(integration_session_factory, old_id, root_id)

        resp = await integration_client.get(f"/oil-gas-fields/{old_id}/detail")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == root_id
        assert body["requested_resource_id"] == old_id
        # Real data from the root, not the old resource's null shell.
        assert body["data"]["name"] == "Merged Root"

    @pytest.mark.anyio
    async def test_plain_get_resolves_to_root_with_flag(
        self,
        integration_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        og_create_res_fact: ResourceCreateFactory,
    ):
        root_id = await self._create(
            integration_client, og_create_res_fact, "Merged Root"
        )
        old_id = await self._create(integration_client, og_create_res_fact, "Old Shell")
        await self._repoint(integration_session_factory, old_id, root_id)

        resp = await integration_client.get(f"/oil-gas-fields/{old_id}")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == root_id
        assert body["requested_resource_id"] == old_id
        assert body["name"] == "Merged Root"

    @pytest.mark.anyio
    async def test_live_resource_has_null_flag(
        self,
        integration_client: AsyncClient,
        og_create_res_fact: ResourceCreateFactory,
    ):
        root_id = await self._create(integration_client, og_create_res_fact, "Live")

        resp = await integration_client.get(f"/oil-gas-fields/{root_id}/detail")

        assert resp.status_code == 200, resp.text
        assert resp.json()["requested_resource_id"] is None
