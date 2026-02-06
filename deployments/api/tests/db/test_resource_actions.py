"""Database integration tests for resource_actions module."""

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db import resource_actions
from stitch.api.db.model import (
    GemSourceModel,
    MembershipModel,
    ResourceModel,
)
from stitch.api.entities import CreateSourceData, GemData, User, WMData

from tests.utils import (
    make_create_resource,
    make_empty_resource,
    make_gem_data,
    make_resource_with_existing_ids,
    make_resource_with_mixed_sources,
    make_resource_with_new_sources,
    make_rmi_data,
    make_source_data,
    make_wm_data,
)


class TestGetResourceActionUnit: ...


class TestCreateResourceActionUnit: ...


class TestCreateSourceDataActionUnit: ...


class TestCreateResourceActionIntegration:
    """Integration tests for resource_actions.create() with real database."""

    @pytest.mark.anyio
    async def test_creates_resource_with_no_source_data(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Resource with no source data persists correctly."""
        resource_in = make_empty_resource(name="Empty Resource", country="USA")

        result = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=resource_in.model,
        )

        assert result.id is not None
        assert result.name == "Empty Resource"
        assert result.country == "USA"

        db_resource = await seeded_integration_session.get(ResourceModel, result.id)
        assert db_resource is not None
        assert db_resource.name == "Empty Resource"

        membership_count = (
            await seeded_integration_session.execute(
                select(func.count()).select_from(MembershipModel)
            )
        ).scalar()
        assert membership_count == 0

    @pytest.mark.anyio
    async def test_creates_resource_with_new_gem_source(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """New GEM source creates resource, source, and membership."""
        resource_in = make_resource_with_new_sources(
            gem=make_gem_data(
                name="Test GEM Field", latitude=40.0, longitude=-100.0
            ).model,
            name="With GEM",
        )

        result = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=resource_in.model,
        )

        assert result.id is not None
        assert result.name == "With GEM"

        gem_sources = (
            (
                await seeded_integration_session.execute(
                    select(GemSourceModel).where(
                        GemSourceModel.name == "Test GEM Field"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(gem_sources) == 1

        memberships = (
            (
                await seeded_integration_session.execute(
                    select(MembershipModel).where(
                        MembershipModel.resource_id == result.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(memberships) == 1
        assert memberships[0].source == "gem"

    @pytest.mark.anyio
    async def test_creates_resource_with_new_sources_all_types(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Resource with all three source types creates correct memberships."""
        source_data = make_source_data(
            gem=[make_gem_data(name="All Types GEM").model],
            wm=[make_wm_data(name="All Types WM").model],
            rmi=[make_rmi_data(name="All Types RMI").model],
        )
        resource_in = make_create_resource(
            name="All Sources Resource",
            source_data=source_data,
        )

        result = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=resource_in.model,
        )

        memberships = (
            (
                await seeded_integration_session.execute(
                    select(MembershipModel).where(
                        MembershipModel.resource_id == result.id
                    )
                )
            )
            .scalars()
            .all()
        )

        sources = {m.source for m in memberships}
        assert sources == {"gem", "wm", "rmi"}

    @pytest.mark.anyio
    async def test_creates_resource_with_existing_gem_id(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        existing_gem_source: GemSourceModel,
    ):
        """Existing source ID creates membership without new source record."""
        resource_in = make_resource_with_existing_ids(
            gem_ids=[existing_gem_source.id],
            name="With Existing GEM",
        )

        result = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=resource_in.model,
        )

        assert result.id is not None

        memberships = (
            (
                await seeded_integration_session.execute(
                    select(MembershipModel).where(
                        MembershipModel.resource_id == result.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(memberships) == 1
        assert memberships[0].source_pk == existing_gem_source.id

    @pytest.mark.anyio
    async def test_creates_resource_with_mixed_new_and_existing(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        existing_gem_source: GemSourceModel,
    ):
        """Mix of new sources and existing IDs creates correct memberships."""
        new_gem = make_gem_data(name="Brand New GEM").model

        resource_in = make_resource_with_mixed_sources(
            new_gem=new_gem,
            existing_gem_ids=[existing_gem_source.id],
            name="Mixed Sources",
        )

        result = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=resource_in.model,
        )

        memberships = (
            (
                await seeded_integration_session.execute(
                    select(MembershipModel).where(
                        MembershipModel.resource_id == result.id
                    )
                )
            )
            .scalars()
            .all()
        )

        gem_memberships = [m for m in memberships if m.source == "gem"]
        assert len(gem_memberships) == 2

    @pytest.mark.anyio
    async def test_creates_resource_with_multiple_sources_same_type(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Multiple sources of same type creates multiple memberships."""
        gems = [make_gem_data(name=f"Multi GEM {i}").model for i in range(3)]
        resource_in = make_resource_with_new_sources(gem=gems, name="Multiple GEMs")

        result = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=resource_in.model,
        )

        memberships = (
            (
                await seeded_integration_session.execute(
                    select(MembershipModel).where(
                        MembershipModel.resource_id == result.id
                    )
                )
            )
            .scalars()
            .all()
        )

        assert len(memberships) == 3
        assert all(m.source == "gem" for m in memberships)

    @pytest.mark.anyio
    async def test_nonexistent_source_id_creates_no_membership(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Nonexistent source ID is skipped, no membership created."""
        resource_in = make_resource_with_existing_ids(
            gem_ids=[99999],
            name="With Bad ID",
        )

        result = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=resource_in.model,
        )

        assert result.id is not None

        memberships = (
            (
                await seeded_integration_session.execute(
                    select(MembershipModel).where(
                        MembershipModel.resource_id == result.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(memberships) == 0

    @pytest.mark.anyio
    async def test_source_can_be_linked_to_multiple_resources(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        existing_gem_source: GemSourceModel,
    ):
        """Verify many-to-many: same source record can belong to multiple resources."""
        resource1_in = make_resource_with_existing_ids(
            gem_ids=[existing_gem_source.id],
            name="First Resource",
        )
        result1 = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=resource1_in.model,
        )

        resource2_in = make_resource_with_existing_ids(
            gem_ids=[existing_gem_source.id],
            name="Second Resource",
        )
        result2 = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=resource2_in.model,
        )

        memberships = (
            (
                await seeded_integration_session.execute(
                    select(MembershipModel).where(
                        MembershipModel.source == "gem",
                        MembershipModel.source_pk == existing_gem_source.id,
                    )
                )
            )
            .scalars()
            .all()
        )

        assert len(memberships) == 2
        resource_ids = {m.resource_id for m in memberships}
        assert resource_ids == {result1.id, result2.id}


class TestGetResourceActionIntegration:
    """Integration tests for resource_actions.get() with real database."""

    @pytest.mark.anyio
    async def test_get_returns_resource_with_populated_source_data(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """GET returns resource with source_data populated."""
        resource_in = make_resource_with_new_sources(
            gem=make_gem_data(name="Get Test GEM").model,
            name="Get Test",
        )

        created = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=resource_in.model,
        )

        result = await resource_actions.get(
            session=seeded_integration_session,
            id=created.id,
        )

        assert result.name == "Get Test"
        assert len(result.source_data.gem) == 1

    @pytest.mark.anyio
    async def test_get_nonexistent_raises_404(
        self,
        seeded_integration_session: AsyncSession,
    ):
        """GET nonexistent resource raises HTTPException with 404."""
        with pytest.raises(HTTPException) as exc_info:
            await resource_actions.get(
                session=seeded_integration_session,
                id=99999,
            )

        assert exc_info.value.status_code == 404


class TestCreateSourceDataActionIntegration:
    """Integration tests for resource_actions.create_source_data()."""

    @pytest.mark.anyio
    async def test_bulk_creates_sources_returns_source_data_with_ids(
        self,
        seeded_integration_session: AsyncSession,
    ):
        """Bulk create sources returns SourceData with assigned IDs."""
        source_data = CreateSourceData(
            gem=[
                GemData(
                    name="Bulk GEM 1", latitude=40.0, longitude=-100.0, country="USA"
                ),
                GemData(
                    name="Bulk GEM 2", latitude=41.0, longitude=-101.0, country="CAN"
                ),
            ],
            wm=[
                WMData(name="Bulk WM", country="USA"),
            ],
        )

        result = await resource_actions.create_source_data(
            session=seeded_integration_session,
            data=source_data,
        )

        assert len(result.gem) == 2
        assert len(result.wm) == 1

        for gem in result.gem.values():
            assert gem.id is not None

        db_gems = (
            (
                await seeded_integration_session.execute(
                    select(GemSourceModel).where(GemSourceModel.name.like("Bulk GEM%"))
                )
            )
            .scalars()
            .all()
        )
        assert len(db_gems) == 2
