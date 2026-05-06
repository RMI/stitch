"""Database integration tests for og_field_source_actions query/count."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db import og_field_source_actions as source_actions
from stitch.api.entities import (
    OGFieldQueryParams,
    User,
)
from tests.factories import ResourceCreateFactory


_QueryParams = OGFieldQueryParams


class TestSourceQueryAction:
    """Integration tests for source_actions.query() and count()."""

    @pytest.fixture
    async def seeded_sources(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        og_create_res_fact: ResourceCreateFactory,
    ):
        """Create 3 resources (each with sources + active memberships)."""
        for name in ["Alpha", "Bravo", "Charlie"]:
            await resource_actions.create(
                session=seeded_integration_session,
                user=test_user,
                resource=og_create_res_fact(name=name),
            )

    @pytest.mark.anyio
    async def test_query_paginates(
        self,
        seeded_integration_session: AsyncSession,
        seeded_sources,
    ):
        params = _QueryParams(page=1, page_size=2)
        items, total = await source_actions.query(seeded_integration_session, params)

        assert total > 0
        assert len(items) == min(2, total)

    @pytest.mark.anyio
    async def test_query_empty_table(
        self,
        seeded_integration_session: AsyncSession,
    ):
        items, total = await source_actions.query(
            seeded_integration_session, _QueryParams()
        )
        assert total == 0
        assert len(items) == 0
