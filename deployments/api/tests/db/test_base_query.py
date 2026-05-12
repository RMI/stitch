"""Integration tests for OGFieldQueryMixin query helpers against OilGasFieldSourceModel."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db.model import OilGasFieldSourceModel
from stitch.api.entities import (
    OGFieldQueryParams,
    OGFieldSortParams,
    User,
)
from tests.utils import make_source_record


@pytest.fixture
async def seeded_sources(
    seeded_integration_session: AsyncSession,
    test_user: User,
):
    """Seed 8 diverse source rows for query testing."""
    session = seeded_integration_session
    uid = test_user.id
    sources = [
        OilGasFieldSourceModel(
            source="gem",
            name="Permian Basin",
            country="USA",
            field_status="Producing",
            basin="Permian",
            region="Texas",
            source_record=make_source_record(payload={"source": "gem"}),
            source_record_hash="hash-gem-1",
            discovery_year=1920,
            created_by_id=uid,
            last_updated_by_id=uid,
        ),
        OilGasFieldSourceModel(
            source="wm",
            name="Ghawar",
            country="SAU",
            field_status="Producing",
            location_type="Onshore",
            source_record=make_source_record(payload={"source": "wm"}),
            source_record_hash="hash-wm-1",
            discovery_year=1948,
            created_by_id=uid,
            last_updated_by_id=uid,
        ),
        OilGasFieldSourceModel(
            source="gem",
            name="Vaca Muerta",
            country="ARG",
            field_status="Producing",
            basin="Neuquen",
            production_conventionality="Unconventional",
            source_record=make_source_record(payload={"source": "gem"}),
            source_record_hash="hash-gem-2",
            created_by_id=uid,
            last_updated_by_id=uid,
        ),
        OilGasFieldSourceModel(
            source="rmi",
            name="Prudhoe Bay",
            country="USA",
            field_status="Non-Producing",
            region="Alaska",
            source_record=make_source_record(payload={"source": "rmi"}),
            source_record_hash="hash-rmi-1",
            discovery_year=1968,
            created_by_id=uid,
            last_updated_by_id=uid,
        ),
        OilGasFieldSourceModel(
            source="wm",
            name="Kashagan",
            country="KAZ",
            field_status="Producing",
            location_type="Offshore",
            source_record=make_source_record(payload={"source": "wm"}),
            source_record_hash="hash-wm-2",
            discovery_year=2000,
            created_by_id=uid,
            last_updated_by_id=uid,
        ),
        OilGasFieldSourceModel(
            source="gem",
            name="permskiy basseyn",
            country="RUS",
            name_local="\u043f\u0435\u0440\u043c\u0441\u043a\u0438\u0439 \u0431\u0430\u0441\u0441\u0435\u0439\u043d",
            field_status="Abandoned",
            source_record=make_source_record(payload={"source": "gem"}),
            source_record_hash="hash-gem-3",
            created_by_id=uid,
            last_updated_by_id=uid,
        ),
        OilGasFieldSourceModel(
            source="llm",
            name="Daqing",
            country="CHN",
            field_status="Producing",
            source_record=make_source_record(payload={"source": "llm"}),
            source_record_hash="hash-llm-1",
            discovery_year=1959,
            created_by_id=uid,
            last_updated_by_id=uid,
        ),
        OilGasFieldSourceModel(
            source="gem",
            name="Permian Delaware",
            country="USA",
            field_status="Producing",
            basin="Permian",
            state_province="New Mexico",
            source_record=make_source_record(payload={"source": "gem"}),
            source_record_hash="hash-gem-4",
            created_by_id=uid,
            last_updated_by_id=uid,
        ),
    ]
    session.add_all(sources)
    await session.flush()
    return sources


async def _execute(session: AsyncSession, **overrides):
    """Helper: build and execute a query using the mixin's building blocks directly."""
    params = OGFieldQueryParams(**overrides)
    M = OilGasFieldSourceModel

    base = select(M).distinct()
    for cond in M._build_conditions(params):
        base = base.where(cond)
    base = base.order_by(*M._create_sort_clauses(params))

    total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
    stmt = M._apply_pagination(base, params)
    rows = (await session.scalars(stmt)).all()
    return rows, total


class TestBaseQuerySubstringSearch:
    """Tests for q= substring matching across text fields."""

    @pytest.mark.anyio
    async def test_q_matches_name_and_name_local(
        self,
        seeded_integration_session,
        seeded_sources,
    ):
        """q='perm' matches 'Permian Basin', 'Permian Delaware', 'permskiy basseyn'."""
        rows, total = await _execute(
            seeded_integration_session,
            q="perm",
        )
        names = {r.name for r in rows}
        assert total == 3
        assert {"Permian Basin", "Permian Delaware", "permskiy basseyn"} == names

    @pytest.mark.anyio
    async def test_q_combined_with_exact_filter(
        self,
        seeded_integration_session,
        seeded_sources,
    ):
        """q='perm' + country='USA' narrows to 2 results."""
        rows, total = await _execute(
            seeded_integration_session,
            q="perm",
            country="USA",
        )
        names = {r.name for r in rows}
        assert total == 2
        assert {"Permian Basin", "Permian Delaware"} == names


class TestBaseQueryExactFilters:
    """Tests for exact-match equality filters."""

    @pytest.mark.anyio
    async def test_multiple_filters_and(
        self,
        seeded_integration_session,
        seeded_sources,
    ):
        """country=USA AND field_status=Producing returns Permian Basin, Permian Delaware."""
        rows, total = await _execute(
            seeded_integration_session,
            country="USA",
            field_status="Producing",
        )
        names = {r.name for r in rows}
        assert total == 2
        assert {"Permian Basin", "Permian Delaware"} == names

    @pytest.mark.anyio
    async def test_no_matches(
        self,
        seeded_integration_session,
        seeded_sources,
    ):
        """country=XYZ returns empty."""
        rows, total = await _execute(
            seeded_integration_session,
            country="XYZ",
        )
        assert total == 0
        assert len(rows) == 0

    @pytest.mark.anyio
    async def test_id_exact_match(
        self,
        seeded_integration_session,
        seeded_sources,
    ):
        """id filter returns a single matching row."""
        target = seeded_sources[0]
        rows, total = await _execute(
            seeded_integration_session,
            id=target.id,
        )
        assert total == 1
        assert len(rows) == 1
        assert rows[0].id == target.id

    @pytest.mark.anyio
    async def test_empty_q_ignored(
        self,
        seeded_integration_session,
        seeded_sources,
    ):
        """q='' treated as no search, returns all 8."""
        rows, total = await _execute(
            seeded_integration_session,
            q="",
        )
        assert total == 8


class TestBaseQuerySortAndPagination:
    """Tests for sorting and pagination."""

    @pytest.mark.anyio
    async def test_sort_and_paginate(
        self,
        seeded_integration_session,
        seeded_sources,
    ):
        """Sort by discovery_year asc, page_size=3 returns first 3 non-null years."""
        rows, total = await _execute(
            seeded_integration_session,
            sort_by="discovery_year",
            sort_order="asc",
            page=1,
            page_size=3,
        )
        assert total == 8
        assert len(rows) == 3
        years = [r.discovery_year for r in rows]
        assert years == [1920, 1948, 1959]

    @pytest.mark.anyio
    async def test_combined_filter_sort_paginate(
        self,
        seeded_integration_session,
        seeded_sources,
    ):
        """q=perm + field_status=Producing + sort by name desc + page_size=1."""
        rows, total = await _execute(
            seeded_integration_session,
            q="perm",
            field_status="Producing",
            sort_by="name",
            sort_order="desc",
            page=1,
            page_size=1,
        )
        assert total == 2
        assert len(rows) == 1
        assert rows[0].name == "Permian Delaware"

    @pytest.mark.anyio
    async def test_invalid_sort_field_raises(self):
        """OGFieldSortParams with invalid sort_by raises ValidationError."""
        with pytest.raises(Exception):
            OGFieldSortParams(sort_by="owners")
