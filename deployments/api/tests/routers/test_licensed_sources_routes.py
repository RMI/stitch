"""Route-level integration tests for licensed-source filtering."""

from collections.abc import AsyncIterator, Callable, Collection
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.auth import TokenClaims
from stitch.auth.permissions import RESOURCE_READ, SOURCE_READ_GEM, SOURCE_READ_PREFIX

from stitch.api.auth import get_current_user, get_token_claims
from stitch.api.db.config import UnitOfWork, get_uow
from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    OilGasFieldSourceModel,
    ResourceModel,
    UserModel,
)
from stitch.api import permissions as api_permissions
from stitch.api.db.read_model.permissions import PUBLIC_SOURCES
from stitch.api.db.read_model.state import refresh_resource_states
from stitch.api.entities import User
from stitch.api.main import app
from tests.utils import make_source_model, make_source_record


def _gem_only_claims() -> TokenClaims:
    return TokenClaims(
        sub="test|user-1",
        email="test@test.com",
        name="Test User",
        permissions=frozenset({RESOURCE_READ, SOURCE_READ_GEM}),
    )


def _resource_only_claims() -> TokenClaims:
    return TokenClaims(
        sub="test|user-1",
        email="test@test.com",
        name="Test User",
        permissions=frozenset({RESOURCE_READ}),
    )


_PUBLIC_SOURCE_READS = frozenset(f"{SOURCE_READ_PREFIX}{s}" for s in PUBLIC_SOURCES)

type ClientFactory = Callable[
    [Collection[str]], AbstractAsyncContextManager[AsyncClient]
]


@pytest.fixture
async def client_with(
    integration_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_user_model: UserModel,
) -> ClientFactory:
    """Make clients whose token holds exactly the given permissions."""
    async with integration_session_factory() as session:
        session.add(test_user_model)
        await session.commit()

    async def override_get_uow() -> AsyncIterator[UnitOfWork]:
        async with UnitOfWork(integration_session_factory) as uow:
            yield uow

    @asynccontextmanager
    async def make(permissions: Collection[str]) -> AsyncIterator[AsyncClient]:
        claims = TokenClaims(
            sub="test|user-1",
            email="test@test.com",
            name="Test User",
            permissions=frozenset(permissions),
        )
        app.dependency_overrides[get_uow] = override_get_uow
        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_token_claims] = lambda: claims
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test/api/v1"
        ) as ac:
            yield ac

    return make


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


@pytest.fixture
async def resource_only_client(
    integration_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_user_model: UserModel,
) -> AsyncIterator[AsyncClient]:
    """Client with resource read but no source read grants."""
    async with integration_session_factory() as session:
        session.add(test_user_model)
        await session.commit()

    async def override_get_uow() -> AsyncIterator[UnitOfWork]:
        async with UnitOfWork(integration_session_factory) as uow:
            yield uow

    def override_get_current_user() -> User:
        return test_user

    def override_get_token_claims() -> TokenClaims:
        return _resource_only_claims()

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
            attrs = {k: v for k, v in row.items() if k != "source"}
            source = make_source_model(
                source=row["source"],
                created_by_id=user.id,
                source_record=make_source_record(payload=row).model_dump(mode="json"),
                **attrs,
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
        await session.flush()
        # Seeded directly, not through a write action: bring the read model the
        # list reads from up to date, as the write actions do.
        await refresh_resource_states(session, [resource.id])
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
    @pytest.mark.parametrize(
        "permissions",
        [
            pytest.param({RESOURCE_READ}, id="no source grants"),
            pytest.param({RESOURCE_READ, SOURCE_READ_GEM}, id="one public source"),
            pytest.param(
                {RESOURCE_READ, *_PUBLIC_SOURCE_READS} - {f"{SOURCE_READ_PREFIX}nor"},
                id="all public sources but one",
            ),
        ],
    )
    @pytest.mark.parametrize(
        "path", ["/oil-gas-fields/", "/oil-gas-fields/filter-options"]
    )
    async def test_callers_missing_a_public_source_are_refused(
        self,
        client_with: ClientFactory,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
        permissions: set[str],
        path: str,
    ):
        """The list is served from precomputed rows for exact permission
        profiles, all of which include every public source."""
        await _seed_resource_with_sources(
            integration_session_factory,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
        )

        async with client_with(permissions) as client:
            response = await client.get(path)

        assert response.status_code == 403
        assert "missing read access to public source" in response.json()["detail"]

    @pytest.mark.anyio
    async def test_list_returns_only_licensed_data(
        self,
        client_with: ClientFactory,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ):
        gem_id = await _seed_resource_with_sources(
            integration_session_factory,
            test_user,
            {"source": "wm", "name": "WM Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "country": "CAN"},
        )
        wm_only_id = await _seed_resource_with_sources(
            integration_session_factory,
            test_user,
            {"source": "wm", "name": "Only WM", "country": "USA"},
        )

        async with client_with({RESOURCE_READ, *_PUBLIC_SOURCE_READS}) as client:
            response = await client.get("/oil-gas-fields/")

        assert response.status_code == 200
        data = response.json()
        items = {item["id"]: item for item in data["items"]}
        assert set(items.keys()) == {gem_id, wm_only_id}

        gem_item = items[gem_id]
        assert gem_item["data"]["name"] == "GEM Name"
        assert gem_item["data"]["country"] == "CAN"
        assert gem_item["provenance"]["name"] == "gem"

        null_item = items[wm_only_id]
        assert null_item["data"]["name"] is None
        assert null_item["data"]["country"] is None
        assert null_item["provenance"]["name"] is None

    @pytest.mark.anyio
    async def test_list_with_explicit_unlicensed_source_returns_existence_with_null_fields(
        self,
        client_with: ClientFactory,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ):
        resource_id = await _seed_resource_with_sources(
            integration_session_factory,
            test_user,
            {"source": "wm", "name": "WM Name", "country": "USA"},
        )

        async with client_with({RESOURCE_READ, *_PUBLIC_SOURCE_READS}) as client:
            response = await client.get("/oil-gas-fields/?source=wm")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        item = data["items"][0]
        assert item["id"] == resource_id
        assert item["data"]["name"] is None
        assert item["data"]["country"] is None
        assert item["provenance"]["name"] is None

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "path", ["/oil-gas-fields/", "/oil-gas-fields/filter-options"]
    )
    async def test_a_source_the_code_does_not_know_is_ignored(
        self,
        client_with: ClientFactory,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
        path: str,
    ):
        """``licensed_sources`` drops unknown ``source:read:<key>`` grants, so
        the caller is matched on the rest: the public profile here."""
        await _seed_resource_with_sources(
            integration_session_factory,
            test_user,
            {"source": "wm", "name": "WM Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "country": "CAN"},
        )
        public = {RESOURCE_READ, *_PUBLIC_SOURCE_READS}

        async with client_with(public) as client:
            expected = await client.get(path)
        async with client_with(public | {f"{SOURCE_READ_PREFIX}foo"}) as client:
            response = await client.get(path)

        assert response.status_code == 200
        assert response.json() == expected.json()

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "path", ["/oil-gas-fields/", "/oil-gas-fields/filter-options"]
    )
    async def test_a_source_not_in_any_profile_is_refused(
        self,
        client_with: ClientFactory,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
        path: str,
    ):
        """A source added to the code but not yet classified as public or
        restricted (``read_model.permissions``) matches no stored profile."""
        monkeypatch.setattr(
            api_permissions,
            "_VALID_SOURCES",
            api_permissions._VALID_SOURCES | {"foo"},
        )
        await _seed_resource_with_sources(
            integration_session_factory,
            test_user,
            {"source": "gem", "name": "GEM Name", "country": "CAN"},
        )

        permissions = {
            RESOURCE_READ,
            *_PUBLIC_SOURCE_READS,
            f"{SOURCE_READ_PREFIX}foo",
        }
        async with client_with(permissions) as client:
            response = await client.get(path)

        assert response.status_code == 403
        assert "a source the list can't serve yet" in response.json()["detail"]

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
        assert "source_record" not in data["source_data"][0]


class TestOilGasFieldSourcesLicensedSources:
    @pytest.mark.anyio
    async def test_list_with_no_source_grants_returns_403(
        self,
        resource_only_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ):
        await _seed_resource_with_sources(
            integration_session_factory,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
        )

        response = await resource_only_client.get("/oil-gas-field-sources/")

        assert response.status_code == 403
        assert "source:read:" in response.json()["detail"]

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
        assert "source_record" not in data["items"][0]

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
        assert "source_record" not in data

    @pytest.mark.anyio
    async def test_get_licensed_source_detail_returns_source_record(
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

        response = await gem_only_client.get(
            f"/oil-gas-field-sources/{gem_source_id}/detail"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "gem"
        assert data["source_record"]["producer"] == "test-producer"

    @pytest.mark.anyio
    async def test_get_unlicensed_source_detail_returns_404(
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

        response = await gem_only_client.get(
            f"/oil-gas-field-sources/{rmi_source_id}/detail"
        )

        assert response.status_code == 404
