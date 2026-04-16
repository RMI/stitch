"""Integration tests for resource_coalesced_view correctness."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db.model import (
    OilGasFieldSourceModel,
    ResourceModel,
    MembershipModel,
)
from stitch.api.db.model.resource_coalesced_view import ResourceCoalescedView
from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.entities import User


async def _create_resource_with_sources(session, user, source_models):
    resource = ResourceModel.create(created_by=user)
    session.add(resource)
    await session.flush()
    for src in source_models:
        mem = MembershipModel.create(
            created_by=user,
            resource_id=resource.id,
            source=src.source,
            source_pk=src.id,
        )
        session.add(mem)
    await session.flush()
    return resource


@pytest.fixture
async def view_seed_data(seeded_integration_session: AsyncSession, test_user: User):
    """Seed sources and resources:

    s1: gem  - name="Permian Basin", country="USA", basin="Permian", discovery_year=1920
    s2: rmi  - name="Prudhoe Bay", country="USA", discovery_year=1968, basin=None
    s3: wm   - name="Ghawar", country="SAU", discovery_year=1948
    s4: llm  - name="Daqing", country="CHN", discovery_year=1959, basin="Songliao"

    R1: [s1(gem), s2(rmi)] -> name="Prudhoe Bay" (rmi wins), basin="Permian" (gem fills null)
    R2: [s3(wm), s4(llm)]  -> name="Ghawar" (wm wins), basin="Songliao" (llm fills null)
    """
    session = seeded_integration_session
    s1 = OilGasFieldSourceModel(
        source="gem",
        name="Permian Basin",
        country="USA",
        basin="Permian",
        discovery_year=1920,
        created_by_id=test_user.id,
        last_updated_by_id=test_user.id,
    )
    s2 = OilGasFieldSourceModel(
        source="rmi",
        name="Prudhoe Bay",
        country="USA",
        discovery_year=1968,
        created_by_id=test_user.id,
        last_updated_by_id=test_user.id,
    )
    s3 = OilGasFieldSourceModel(
        source="wm",
        name="Ghawar",
        country="SAU",
        discovery_year=1948,
        created_by_id=test_user.id,
        last_updated_by_id=test_user.id,
    )
    s4 = OilGasFieldSourceModel(
        source="llm",
        name="Daqing",
        country="CHN",
        discovery_year=1959,
        basin="Songliao",
        created_by_id=test_user.id,
        last_updated_by_id=test_user.id,
    )
    session.add_all([s1, s2, s3, s4])
    await session.flush()

    r1 = await _create_resource_with_sources(session, test_user, [s1, s2])
    r2 = await _create_resource_with_sources(session, test_user, [s3, s4])
    return {"r1": r1, "r2": r2, "sources": [s1, s2, s3, s4]}


class TestResourceCoalescedView:
    @pytest.mark.anyio
    async def test_priority_resolution(
        self, seeded_integration_session, view_seed_data
    ):
        """RMI source values win over GEM for R1."""
        session = seeded_integration_session
        row = await session.scalar(
            select(ResourceCoalescedView).where(
                ResourceCoalescedView.id == view_seed_data["r1"].id
            )
        )
        assert row is not None
        assert row.name == "Prudhoe Bay"
        assert row.country == "USA"

    @pytest.mark.anyio
    async def test_null_fallthrough(self, seeded_integration_session, view_seed_data):
        """Higher-priority null falls through to lower-priority."""
        session = seeded_integration_session
        row = await session.scalar(
            select(ResourceCoalescedView).where(
                ResourceCoalescedView.id == view_seed_data["r1"].id
            )
        )
        assert row.basin == "Permian"

        row2 = await session.scalar(
            select(ResourceCoalescedView).where(
                ResourceCoalescedView.id == view_seed_data["r2"].id
            )
        )
        assert row2.basin == "Songliao"

    @pytest.mark.anyio
    async def test_repointed_excluded(
        self, seeded_integration_session, test_user, view_seed_data
    ):
        """Repointed resources do not appear in the view."""
        session = seeded_integration_session
        r1 = view_seed_data["r1"]
        r1.repointed_id = view_seed_data["r2"].id
        await session.flush()

        rows = (await session.scalars(select(ResourceCoalescedView))).all()
        assert r1.id not in {r.id for r in rows}


class TestViewFreshnessAfterMutations:
    @pytest.mark.anyio
    async def test_new_resource_appears_in_view(
        self, seeded_integration_session, test_user
    ):
        """A newly created resource with sources appears in the view."""
        session = seeded_integration_session
        s1 = OilGasFieldSourceModel(
            source="gem",
            name="New Field",
            country="BRA",
            created_by_id=test_user.id,
            last_updated_by_id=test_user.id,
        )
        session.add(s1)
        await session.flush()
        resource = await _create_resource_with_sources(session, test_user, [s1])
        row = await session.scalar(
            select(ResourceCoalescedView).where(ResourceCoalescedView.id == resource.id)
        )
        assert row is not None
        assert row.name == "New Field"
        assert row.country == "BRA"

    @pytest.mark.anyio
    async def test_merge_updates_view(
        self, seeded_integration_session, test_user, view_seed_data
    ):
        """Merged resources disappear; new merged resource appears."""
        session = seeded_integration_session
        r1, r2 = view_seed_data["r1"], view_seed_data["r2"]
        merged = await resource_actions.apply_resource_merge(
            session=session,
            user=test_user,
            resource_ids=[r1.id, r2.id],
        )
        rows = (await session.scalars(select(ResourceCoalescedView))).all()
        view_ids = {r.id for r in rows}
        assert r1.id not in view_ids
        assert r2.id not in view_ids
        assert merged.id in view_ids
