"""Route-level integration tests for licensed-source filtering."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.auth import TokenClaims

from stitch.api.auth import get_current_user, get_token_claims
from stitch.api.db.config import UnitOfWork, get_uow
from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    OilGasFieldSourceModel,
    ResourceModel,
    UserModel,
)
from stitch.api.entities import User
from stitch.api.main import app


def _gem_only_claims() -> TokenClaims:
    return TokenClaims(
        sub="test|user-1",
        email="test@test.com",
        name="Test User",
        permissions=frozenset({"resource:read:licensed:gem"}),
    )


@pytest.fixture
async def gem_only_client(
    integration_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_user_model: UserModel,
) -> AsyncIterator[AsyncClient]:
    """Client whose token claims license only the `gem` source."""
    async with integration_session_factory() as session:
        session.add(test_user_model)
        await session.commit()

    async def override_get_uow() -> AsyncIterator[UnitOfWork]:
        async with UnitOfWork(integration_session_factory) as uow:
            yield uow

    def override_get_current_user() -> User:
        return test_user

    def override_get_token_claims() -> TokenClaims:
        return _gem_only_claims()

    app.dependency_overrides[get_uow] = override_get_uow
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_token_claims] = override_get_token_claims

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test/api/v1",
    ) as ac:
        yield ac


async def _seed_resource_with_sources(
    session_factory: async_sessionmaker[AsyncSession],
    user: User,
    *source_rows: dict,
) -> int:
    async with session_factory() as session:
        resource = ResourceModel.create(created_by=user)
        session.add(resource)
        await session.flush()
        for row in source_rows:
            source = OilGasFieldSourceModel(
                **row,
                created_by_id=user.id,
                last_updated_by_id=user.id,
            )
            session.add(source)
            await session.flush()
            session.add(
                MembershipModel.create(
                    created_by=user,
                    resource_id=resource.id,
                    source=source.source,
                    source_pk=source.id,
                    status=MembershipStatus.ACTIVE,
                )
            )
        await session.commit()
        return resource.id


async def _source_id_for(
    session_factory: async_sessionmaker[AsyncSession], src: str
) -> int:
    from sqlalchemy import select

    async with session_factory() as session:
        row = (
            await session.execute(
                select(OilGasFieldSourceModel).where(
                    OilGasFieldSourceModel.source == src
                )
            )
        ).scalar_one()
        return row.id


class TestOilGasFieldsLicensedSources:
    @pytest.mark.anyio
    async def test_list_returns_only_licensed_data(
        self,
        gem_only_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ):
        gem_id = await _seed_resource_with_sources(
            integration_session_factory,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "country": "CAN"},
        )
        rmi_only_id = await _seed_resource_with_sources(
            integration_session_factory,
            test_user,
            {"source": "rmi", "name": "Only RMI", "country": "USA"},
        )

        response = await gem_only_client.get("/oil-gas-fields/")

        assert response.status_code == 200
        data = response.json()
        items = {item["id"]: item for item in data["items"]}
        assert set(items.keys()) == {gem_id, rmi_only_id}

        gem_item = items[gem_id]
        assert gem_item["data"]["name"] == "GEM Name"
        assert gem_item["data"]["country"] == "CAN"
        assert gem_item["provenance"]["name"] == "gem"

        null_item = items[rmi_only_id]
        assert null_item["data"]["name"] is None
        assert null_item["data"]["country"] is None
        assert null_item["provenance"]["name"] is None

    @pytest.mark.anyio
    async def test_list_with_explicit_unlicensed_source_returns_existence_with_null_fields(
        self,
        gem_only_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ):
        resource_id = await _seed_resource_with_sources(
            integration_session_factory,
            test_user,
            {"source": "llm", "name": "LLM Name", "country": "USA"},
        )

        response = await gem_only_client.get("/oil-gas-fields/?source=llm")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        item = data["items"][0]
        assert item["id"] == resource_id
        assert item["data"]["name"] is None
        assert item["data"]["country"] is None
        assert item["provenance"]["name"] is None

    @pytest.mark.anyio
    async def test_get_resource_redacts_unlicensed_source_data(
        self,
        gem_only_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ):
        resource_id = await _seed_resource_with_sources(
            integration_session_factory,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "country": "CAN"},
        )

        response = await gem_only_client.get(f"/oil-gas-fields/{resource_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == resource_id
        assert data["name"] == "GEM Name"
        assert data["country"] == "CAN"

    @pytest.mark.anyio
    async def test_get_detail_filters_source_data_to_licensed_only(
        self,
        gem_only_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ):
        resource_id = await _seed_resource_with_sources(
            integration_session_factory,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "country": "CAN"},
        )

        response = await gem_only_client.get(f"/oil-gas-fields/{resource_id}/detail")

        assert response.status_code == 200
        data = response.json()
        sources_in_detail = {sd["source"] for sd in data["source_data"]}
        assert sources_in_detail == {"gem"}
        assert data["data"]["name"] == "GEM Name"


class TestOilGasFieldSourcesLicensedSources:
    @pytest.mark.anyio
    async def test_list_drops_unlicensed_rows(
        self,
        gem_only_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ):
        await _seed_resource_with_sources(
            integration_session_factory,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "country": "CAN"},
        )

        response = await gem_only_client.get("/oil-gas-field-sources/")

        assert response.status_code == 200
        data = response.json()
        sources_returned = {item["source"] for item in data["items"]}
        assert sources_returned == {"gem"}

    @pytest.mark.anyio
    async def test_get_unlicensed_source_returns_404(
        self,
        gem_only_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ):
        await _seed_resource_with_sources(
            integration_session_factory,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
        )
        rmi_source_id = await _source_id_for(integration_session_factory, "rmi")

        response = await gem_only_client.get(f"/oil-gas-field-sources/{rmi_source_id}")

        assert response.status_code == 404

    @pytest.mark.anyio
    async def test_get_licensed_source_returns_200(
        self,
        gem_only_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ):
        await _seed_resource_with_sources(
            integration_session_factory,
            test_user,
            {"source": "gem", "name": "GEM Name", "country": "CAN"},
        )
        gem_source_id = await _source_id_for(integration_session_factory, "gem")

        response = await gem_only_client.get(f"/oil-gas-field-sources/{gem_source_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "gem"
        assert data["name"] == "GEM Name"
