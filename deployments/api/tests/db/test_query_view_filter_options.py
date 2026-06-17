"""Integration tests for filter_options_v2 in og_field_query_view_actions.

Guards with SQLite >= 3.30 (window functions + NULLS LAST).
Ports the meaningful cases from TestResourceFilterOptionsAction and adds an
equivalence harness: filter_options_v2 == filter_options across a matrix of
field x licensed_sources.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db import og_field_query_view_actions as v2
from stitch.api.db.og_field_query_view_refresh import rebuild_all
from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    OilGasFieldSourceModel,
    ResourceModel,
)
from stitch.api.entities import OGFieldFilterOptionsParams, User
from tests.utils import make_source_record


pytestmark = pytest.mark.skipif(
    sqlite3.sqlite_version_info < (3, 30, 0),
    reason="window functions / NULLS LAST need SQLite >= 3.30",
)


async def _create_resource_with_sources(
    session: AsyncSession,
    user: User,
    *source_rows: dict,
) -> int:
    """Seed a ResourceModel + one OilGasFieldSourceModel + MembershipModel per row."""
    resource = ResourceModel.create(created_by=user)
    session.add(resource)
    await session.flush()

    for row in source_rows:
        payload = {
            "source": row["source"],
            "name": row.get("name"),
            "country": row.get("country"),
        }
        source = OilGasFieldSourceModel(
            **row,
            source_record=make_source_record(payload=payload).model_dump(mode="json"),
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
            )
        )

    await session.flush()
    return resource.id


# ---------------------------------------------------------------------------
# Ported TestResourceFilterOptionsAction cases
# ---------------------------------------------------------------------------


class TestFilterOptionsV2:
    @pytest.mark.anyio
    async def test_returns_distinct_sorted_coalesced_values(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Distinct, sorted, coalesced country values; NULL and "" excluded."""
        await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "country": None},
            {"source": "gem", "country": "CAN"},
        )
        await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "country": "USA"},
        )
        await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "country": ""},
        )
        await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "country": None},
        )
        await rebuild_all(seeded_integration_session)

        values = await v2.filter_options_v2(
            seeded_integration_session,
            OGFieldFilterOptionsParams(field="country"),
        )

        assert values == ["CAN", "USA"]

    @pytest.mark.anyio
    async def test_honors_licensed_sources_after_coalescing(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Only coalesced values from licensed sources are returned."""
        await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "country": None},
            {"source": "gem", "country": "CAN"},
        )
        await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "country": "USA"},
        )
        await rebuild_all(seeded_integration_session)

        values = await v2.filter_options_v2(
            seeded_integration_session,
            OGFieldFilterOptionsParams(field="country"),
            licensed_sources=frozenset({"gem", "wm", "llm"}),
        )

        assert values == ["CAN"]

    @pytest.mark.anyio
    async def test_excludes_repointed_and_inactive_memberships(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Repointed resources and inactive memberships are excluded.

        NOTE: rebuild_all is called AFTER mutations so the projection reflects
        current DB state.
        """
        active_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "country": "USA"},
        )
        repointed_to_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "country": "BRA"},
        )
        inactive_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "country": "CAN"},
        )

        # Mutate state BEFORE rebuild_all.
        repointed_resource = await seeded_integration_session.get(
            ResourceModel, repointed_to_id
        )
        assert repointed_resource is not None
        repointed_resource.repointed_id = active_id

        inactive_membership = await seeded_integration_session.scalar(
            select(MembershipModel).where(MembershipModel.resource_id == inactive_id)
        )
        assert inactive_membership is not None
        inactive_membership.status = MembershipStatus.INACTIVE
        await seeded_integration_session.flush()

        # Rebuild AFTER mutation.
        await rebuild_all(seeded_integration_session)

        values = await v2.filter_options_v2(
            seeded_integration_session,
            OGFieldFilterOptionsParams(field="country"),
        )

        assert values == ["USA"]

    @pytest.mark.anyio
    async def test_invalid_field_raises_422(
        self,
        seeded_integration_session: AsyncSession,
    ):
        """Passing an invalid field raises HTTPException 422."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            # bypass Pydantic validation by directly building params with a bad field
            params = OGFieldFilterOptionsParams.model_construct(field="not_a_field")
            await v2.filter_options_v2(seeded_integration_session, params)

        assert exc_info.value.status_code == 422

    @pytest.mark.anyio
    async def test_empty_licensed_sources_returns_empty(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Empty licensed_sources set => no rows => empty list."""
        await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "country": "USA"},
        )
        await rebuild_all(seeded_integration_session)

        values = await v2.filter_options_v2(
            seeded_integration_session,
            OGFieldFilterOptionsParams(field="country"),
            licensed_sources=frozenset(),
        )

        assert values == []


# ---------------------------------------------------------------------------
# Equivalence harness: filter_options_v2 == filter_options
# ---------------------------------------------------------------------------


async def _seed_varied_db(session: AsyncSession, user: User) -> None:
    """Seed a varied DB exercising priority, licensing, nulls, and exclusions."""
    await _create_resource_with_sources(
        session,
        user,
        {
            "source": "rmi",
            "name": "Ghawar",
            "country": "SAU",
            "state_province": "Eastern",
            "region": "Middle East",
            "basin": "Arabian",
            "field_status": "Producing",
        },
        {
            "source": "gem",
            "name": "Ghawar GEM",
            "country": "SAU",
            "basin": "Arabian Basin GEM",
        },
        {
            "source": "wm",
            "name": "Ghawar WM",
            "country": "SAU",
            "basin": "Arabian Basin WM",
        },
    )
    # rmi has null country -> falls through to wm
    await _create_resource_with_sources(
        session,
        user,
        {"source": "rmi", "name": "Burgan", "country": None},
        {"source": "wm", "name": "Burgan WM", "country": "KWT"},
        {"source": "gem", "name": "Burgan GEM", "country": "IRQ"},
    )
    # only wm/llm source
    await _create_resource_with_sources(
        session,
        user,
        {"source": "wm", "name": "Safaniya", "country": "SAU"},
        {"source": "llm", "name": "Safaniya LLM", "country": "USA"},
    )
    # null name, empty country
    await _create_resource_with_sources(
        session,
        user,
        {"source": "gem", "name": None, "country": ""},
    )
    await _create_resource_with_sources(
        session,
        user,
        {"source": "gem", "name": "Alpha", "country": "USA"},
    )
    await _create_resource_with_sources(
        session,
        user,
        {"source": "gem", "name": "Alpha", "country": "MEX"},
    )


_FILTER_FIELD_MATRIX = [
    pytest.param("country", id="field-country"),
    pytest.param("name", id="field-name"),
    pytest.param("basin", id="field-basin"),
    pytest.param("region", id="field-region"),
    pytest.param("state_province", id="field-state-province"),
]

_LICENSE_MATRIX = [
    pytest.param(None, id="lic-none"),
    pytest.param(frozenset(), id="lic-empty"),
    pytest.param(frozenset({"rmi"}), id="lic-rmi"),
    pytest.param(frozenset({"gem", "wm", "llm"}), id="lic-gem-wm-llm"),
]


class TestFilterOptionsV2Equivalence:
    @pytest.mark.anyio
    @pytest.mark.parametrize("field", _FILTER_FIELD_MATRIX)
    @pytest.mark.parametrize("licensed", _LICENSE_MATRIX)
    async def test_filter_options_v2_matches_filter_options(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        field: str,
        licensed,
    ):
        await _seed_varied_db(seeded_integration_session, test_user)
        await rebuild_all(seeded_integration_session)

        params = OGFieldFilterOptionsParams(field=field)

        v2_values = await v2.filter_options_v2(
            seeded_integration_session, params, licensed_sources=licensed
        )
        ref_values = await resource_actions.filter_options(
            seeded_integration_session, params, licensed_sources=licensed
        )

        assert v2_values == ref_values
