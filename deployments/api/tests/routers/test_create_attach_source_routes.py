"""Integration tests for POST /oil-gas-fields/{id}/sources (create + attach)."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.auth import TokenClaims
from stitch.auth.permissions import (
    RESOURCE_READ,
    RESOURCE_WRITE,
    SOURCE_READ_GEM,
    SOURCE_READ_LLM,
    SOURCE_READ_RMI,
    SOURCE_WRITE,
)

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
from tests.utils import make_source_model, make_source_record


def _writer_claims() -> TokenClaims:
    """Can create+attach sources and read the resulting resource/sources."""
    return TokenClaims(
        sub="test|user-1",
        email="test@test.com",
        name="Test User",
        permissions=frozenset(
            {
                RESOURCE_READ,
                RESOURCE_WRITE,
                SOURCE_WRITE,
                SOURCE_READ_RMI,
                SOURCE_READ_GEM,
                SOURCE_READ_LLM,
            }
        ),
    )


@pytest.fixture
async def writer_client(
    integration_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_user_model: UserModel,
) -> AsyncIterator[AsyncClient]:
    async with integration_session_factory() as session:
        session.add(test_user_model)
        await session.commit()

    async def override_get_uow() -> AsyncIterator[UnitOfWork]:
        async with UnitOfWork(integration_session_factory) as uow:
            yield uow

    def override_get_current_user() -> User:
        return test_user

    def override_get_token_claims() -> TokenClaims:
        return _writer_claims()

    app.dependency_overrides[get_uow] = override_get_uow
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_token_claims] = override_get_token_claims

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test/api/v1",
    ) as ac:
        yield ac


async def _seed_empty_resource(
    session_factory: async_sessionmaker[AsyncSession], user: User
) -> int:
    async with session_factory() as session:
        resource = ResourceModel.create(created_by=user)
        session.add(resource)
        await session.flush()
        resource_id = resource.id
        await session.commit()
        return resource_id


async def _seed_resource_with_source(
    session_factory: async_sessionmaker[AsyncSession],
    user: User,
    **source_attrs,
) -> int:
    async with session_factory() as session:
        resource = ResourceModel.create(created_by=user)
        session.add(resource)
        await session.flush()
        source = make_source_model(
            created_by_id=user.id,
            source_record=make_source_record(payload=source_attrs).model_dump(
                mode="json"
            ),
            **source_attrs,
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
        resource_id = resource.id
        await session.commit()
        return resource_id


async def _seed_repointed_resource(
    session_factory: async_sessionmaker[AsyncSession], user: User
) -> int:
    """Create a resource that has been merged away (repointed elsewhere)."""
    async with session_factory() as session:
        canonical = ResourceModel.create(created_by=user)
        session.add(canonical)
        await session.flush()
        merged = ResourceModel.create(created_by=user)
        merged.repointed_id = canonical.id
        session.add(merged)
        await session.flush()
        merged_id = merged.id
        await session.commit()
        return merged_id


def _source_body(source: str = "rmi", **attrs) -> dict:
    # `name` and `country` are required keys on OilGasFieldBase (nullable values).
    body = {
        "source": source,
        "name": None,
        "country": None,
        "source_record": {
            "observed_at": "2026-01-01T00:00:00Z",
            "producer": "test",
            "payload": {},
        },
    }
    body.update(attrs)
    return body


class TestCreateAndAttachSource:
    @pytest.mark.anyio
    async def test_creates_source_and_active_membership(
        self,
        writer_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ):
        resource_id = await _seed_empty_resource(integration_session_factory, test_user)

        response = await writer_client.post(
            f"/oil-gas-fields/{resource_id}/sources",
            json=_source_body("rmi", name="RMI Name", country="USA"),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] is not None
        assert body["source"] == "rmi"
        assert body["name"] == "RMI Name"

        # membership + source persisted
        async with integration_session_factory() as session:
            memberships = (
                (
                    await session.execute(
                        select(MembershipModel).where(
                            MembershipModel.resource_id == resource_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(memberships) == 1
            membership = memberships[0]
            assert membership.status == MembershipStatus.ACTIVE
            assert membership.source == "rmi"
            assert membership.source_pk == body["id"]

            source = await session.get(OilGasFieldSourceModel, body["id"])
            assert source is not None

    @pytest.mark.anyio
    async def test_attached_source_wins_coalescing(
        self,
        writer_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ):
        # gem is lower priority than rmi, so the attached rmi value should win.
        resource_id = await _seed_resource_with_source(
            integration_session_factory,
            test_user,
            source="gem",
            name="Gem Name",
        )

        attach = await writer_client.post(
            f"/oil-gas-fields/{resource_id}/sources",
            json=_source_body("rmi", name="RMI Name"),
        )
        assert attach.status_code == 200

        view = await writer_client.get(f"/oil-gas-fields/{resource_id}")
        assert view.status_code == 200
        assert view.json()["name"] == "RMI Name"

    @pytest.mark.anyio
    async def test_attached_lower_priority_source_loses_coalescing(
        self,
        writer_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ):
        # llm is lower priority than rmi, so attaching an llm value must NOT
        # displace the existing rmi winner.
        resource_id = await _seed_resource_with_source(
            integration_session_factory,
            test_user,
            source="rmi",
            name="RMI Name",
        )

        attach = await writer_client.post(
            f"/oil-gas-fields/{resource_id}/sources",
            json=_source_body("llm", name="LLM Name"),
        )
        assert attach.status_code == 200

        view = await writer_client.get(f"/oil-gas-fields/{resource_id}")
        assert view.status_code == 200
        assert view.json()["name"] == "RMI Name"

    @pytest.mark.anyio
    async def test_missing_resource_returns_404(self, writer_client: AsyncClient):
        response = await writer_client.post(
            "/oil-gas-fields/999999/sources",
            json=_source_body("rmi", name="RMI Name"),
        )
        assert response.status_code == 404

    @pytest.mark.anyio
    async def test_merged_resource_returns_400_and_attaches_nothing(
        self,
        writer_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ):
        # Attaching to a merged (repointed) resource would orphan the source,
        # so it must be rejected without persisting anything.
        resource_id = await _seed_repointed_resource(
            integration_session_factory, test_user
        )

        response = await writer_client.post(
            f"/oil-gas-fields/{resource_id}/sources",
            json=_source_body("rmi", name="RMI Name"),
        )
        assert response.status_code == 400

        # no membership created and no source row leaked (rolled back)
        async with integration_session_factory() as session:
            memberships = (
                (
                    await session.execute(
                        select(MembershipModel).where(
                            MembershipModel.resource_id == resource_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert memberships == []
            sources = (
                (await session.execute(select(OilGasFieldSourceModel))).scalars().all()
            )
            assert sources == []

    @pytest.mark.anyio
    async def test_rejects_client_supplied_source_id(
        self,
        writer_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ):
        resource_id = await _seed_empty_resource(integration_session_factory, test_user)

        response = await writer_client.post(
            f"/oil-gas-fields/{resource_id}/sources",
            json=_source_body("rmi", id=123, name="RMI Name"),
        )
        assert response.status_code == 400
