"""Database integration tests for og_field_source_actions query/count."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from stitch.ogsi.model import GemSourceCreate

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


class TestSourceCreateAction:
    @pytest.mark.anyio
    async def test_create_persists_source_record_and_hash(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        source = GemSourceCreate.model_validate(
            {
                "source": "gem",
                "name": "Alpha",
                "country": "USA",
                "source_record": {
                    "kind": "seed_static",
                    "record_id": None,
                    "run_id": "run-1",
                    "observed_at": "2026-01-01T00:00:00Z",
                    "producer": "stitch-seed@0.1.0",
                    "payload": {"b": 2, "a": 1},
                },
            }
        )

        created = await source_actions.create_source(
            session=seeded_integration_session,
            user=test_user,
            source=source,
        )
        detail = await source_actions.get_source_detail(
            session=seeded_integration_session,
            id=created.id,
        )

        assert created.id is not None
        assert detail.source_record.producer == "stitch-seed@0.1.0"
        assert (
            detail.source_record_hash
            == "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777"
        )

    @pytest.mark.anyio
    async def test_hash_depends_only_on_payload(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        source_a = GemSourceCreate.model_validate(
            {
                "source": "gem",
                "name": "Alpha",
                "country": "USA",
                "source_record": {
                    "kind": "seed_static",
                    "record_id": None,
                    "run_id": "run-1",
                    "observed_at": "2026-01-01T00:00:00Z",
                    "producer": "stitch-seed@0.1.0",
                    "payload": {"a": 1, "b": 2},
                },
            }
        )
        source_b = GemSourceCreate.model_validate(
            {
                "source": "gem",
                "name": "Alpha",
                "country": "USA",
                "source_record": {
                    "kind": "provider",
                    "record_id": "other",
                    "run_id": "run-2",
                    "observed_at": "2026-02-02T00:00:00Z",
                    "producer": "other@2",
                    "payload": {"b": 2, "a": 1},
                },
            }
        )

        created_a = await source_actions.create_source(
            session=seeded_integration_session,
            user=test_user,
            source=source_a,
        )
        created_b = await source_actions.create_source(
            session=seeded_integration_session,
            user=test_user,
            source=source_b,
        )
        detail_a = await source_actions.get_source_detail(
            session=seeded_integration_session,
            id=created_a.id,
        )
        detail_b = await source_actions.get_source_detail(
            session=seeded_integration_session,
            id=created_b.id,
        )

        assert detail_a.source_record_hash == detail_b.source_record_hash
