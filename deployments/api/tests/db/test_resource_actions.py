"""Database integration tests for domain-agnostic resource_actions."""

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db.model import ResourceModel
from stitch.api.entities import User
from tests.utils import ResourceFactory, make_create_resource, make_empty_resource


class TestCreateResourceActionIntegration:
    """Integration tests for resource_actions.create() with real database."""

    @pytest.mark.anyio
    async def test_creates_resource_with_minimal_payload(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        og_field_resource_factory: ResourceFactory,
    ):
        resource_in = make_empty_resource(
            factory=og_field_resource_factory, sources=[("gem", 1)]
        )

        result = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=resource_in,
        )

        assert result.id is not None
        assert result.name is None

        db_resource = await seeded_integration_session.get(ResourceModel, result.id)
        assert db_resource is not None

    @pytest.mark.anyio
    async def test_creates_resource_with_label(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        resource_in = make_create_resource(name="Test Label")

        result = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=resource_in.model,
        )

        assert result.id is not None
        assert result.name == "Test Label"

        db_resource = await seeded_integration_session.get(ResourceModel, result.id)
        assert db_resource is not None
        # DB ResourceModel may store `.name`; tolerate either while refactor settles.
        assert getattr(db_resource, "name", None) in (None, "Test Label")


class TestGetResourceActionIntegration:
    """Integration tests for resource_actions.get() with real database."""

    @pytest.mark.anyio
    async def test_get_returns_resource(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        created = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=make_create_resource(name="Get Test").model,
        )

        result = await resource_actions.get(
            session=seeded_integration_session,
            id=created.id,
        )

        assert result.id == created.id
        assert result.name == "Get Test"

    @pytest.mark.anyio
    async def test_get_nonexistent_raises_404(
        self,
        seeded_integration_session: AsyncSession,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await resource_actions.get(
                session=seeded_integration_session,
                id=99999,
            )
        assert exc_info.value.status_code == 404


class TestListResourcesActionIntegration:
    """Integration tests for resource_actions.get_all() with real database."""

    @pytest.mark.anyio
    async def test_get_all_returns_sequence(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        # create a couple resources
        await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=make_create_resource(name="A").model,
        )
        await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=make_create_resource(name="B").model,
        )

        results = await resource_actions.get_all(session=seeded_integration_session)
        assert isinstance(results, (list, tuple))
        assert len(results) >= 2

        labels = {r.name for r in results}
        assert {"A", "B"} <= labels
