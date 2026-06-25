"""Integration tests for the source-list query path via og_field_source_actions.query."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db import og_field_source_actions as source_actions
from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    ResourceModel,
)
from stitch.api.entities import (
    OGFieldQueryParams,
    OGFieldSortParams,
    User,
)
from tests.utils import make_source_model


@pytest.fixture
async def seeded_sources(
    seeded_integration_session: AsyncSession,
    test_user: User,
):
    """Seed 8 diverse source rows (each with an active membership) for query testing."""
    session = seeded_integration_session
    uid = test_user.id

    def with_record(source: str, **kwargs):
        return make_source_model(source=source, created_by_id=uid, **kwargs)

    sources = [
        with_record(
            "gem",
            name="Permian Basin",
            country="USA",
            field_status="Producing",
            basin="Permian",
            region="Texas",
            discovery_year=1920,
        ),
        with_record(
            "wm",
            name="Ghawar",
            country="SAU",
            field_status="Producing",
            location_type="Onshore",
            discovery_year=1948,
        ),
        with_record(
            "gem",
            name="Vaca Muerta",
            country="ARG",
            field_status="Producing",
            basin="Neuquen",
            production_conventionality="Unconventional",
        ),
        with_record(
            "rmi",
            name="Prudhoe Bay",
            country="USA",
            field_status="Non-Producing",
            region="Alaska",
            discovery_year=1968,
        ),
        with_record(
            "wm",
            name="Kashagan",
            country="KAZ",
            field_status="Producing",
            location_type="Offshore",
            discovery_year=2000,
        ),
        with_record(
            "gem",
            name="permskiy basseyn",
            country="RUS",
            name_local="\u043f\u0435\u0440\u043c\u0441\u043a\u0438\u0439 \u0431\u0430\u0441\u0441\u0435\u0439\u043d",
            field_status="Abandoned",
        ),
        with_record(
            "llm",
            name="Daqing",
            country="CHN",
            field_status="Producing",
            discovery_year=1959,
        ),
        with_record(
            "gem",
            name="Permian Delaware",
            country="USA",
            field_status="Producing",
            basin="Permian",
            state_province="New Mexico",
        ),
    ]
    session.add_all(sources)
    await session.flush()

    # Each source needs an active membership to be visible to the source-list query.
    resource = ResourceModel.create(created_by=test_user)
    session.add(resource)
    await session.flush()
    session.add_all(
        MembershipModel.create(
            created_by=test_user,
            resource_id=resource.id,
            source=src.source,
            source_pk=src.id,
            status=MembershipStatus.ACTIVE,
        )
        for src in sources
    )
    await session.flush()
    return sources


async def _execute(session: AsyncSession, *, licensed_sources=None, **overrides):
    """Run the long-aware source-list query and return coalesced entities + total."""
    params = OGFieldQueryParams(**overrides)
    rows, total = await source_actions.query(
        session, params, licensed_sources=licensed_sources
    )
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


class TestSourceFilter:
    """`source` is a source-path filter (resources cannot filter by source)."""

    @pytest.mark.anyio
    async def test_single_source(self, seeded_integration_session, seeded_sources):
        """source=['gem'] returns only the 4 gem rows."""
        rows, total = await _execute(seeded_integration_session, source=["gem"])
        assert total == 4
        assert {r.source for r in rows} == {"gem"}

    @pytest.mark.anyio
    async def test_multiple_sources(self, seeded_integration_session, seeded_sources):
        """source=['gem','wm'] returns the 4 gem + 2 wm rows."""
        rows, total = await _execute(
            seeded_integration_session, source=["gem", "wm"], page_size=200
        )
        assert total == 6
        assert {r.source for r in rows} == {"gem", "wm"}


class TestLicensedSourcesGating:
    """licensed_sources hides rows whose source is not licensed."""

    @pytest.mark.anyio
    async def test_licensing_hides_unlicensed_rows(
        self, seeded_integration_session, seeded_sources
    ):
        """Only gem rows survive even though params.source defaults to all four."""
        rows, total = await _execute(
            seeded_integration_session,
            licensed_sources=["gem"],
            page_size=200,
        )
        assert total == 4
        assert {r.source for r in rows} == {"gem"}
        assert "Ghawar" not in {r.name for r in rows}  # wm row is hidden


class TestNarrowingProofs:
    """The narrowed pivot really materializes the fields it filters/sorts on."""

    @pytest.mark.anyio
    async def test_filter_by_basin(self, seeded_integration_session, seeded_sources):
        """basin=Permian proves basin is pivoted (two Permian rows)."""
        rows, total = await _execute(seeded_integration_session, basin="Permian")
        assert total == 2
        assert {r.name for r in rows} == {"Permian Basin", "Permian Delaware"}

    @pytest.mark.anyio
    async def test_sort_by_discovery_year_nulls_last(
        self, seeded_integration_session, seeded_sources
    ):
        """discovery_year sorts numerically (from value_num) with NULLs last."""
        rows, total = await _execute(
            seeded_integration_session,
            sort_by="discovery_year",
            sort_order="asc",
            page_size=200,
        )
        assert total == 8
        years = [r.discovery_year for r in rows]
        assert years == [1920, 1948, 1959, 1968, 2000, None, None, None]

    @pytest.mark.anyio
    async def test_empty_involved_orders_by_id(
        self, seeded_integration_session, seeded_sources
    ):
        """sort_by=id, no q/filters: zero value columns, all active rows by id."""
        rows, total = await _execute(
            seeded_integration_session, sort_by="id", page_size=200
        )
        assert total == 8
        ids = [r.id for r in rows]
        assert ids == sorted(ids)


@pytest.fixture
async def tiebreak_sources(
    seeded_integration_session: AsyncSession,
    test_user: User,
):
    """Six gem rows with duplicate (2000) and NULL discovery years + memberships."""
    session = seeded_integration_session
    years = [2000, 2000, None, 1990, None, 2000]
    sources = [
        make_source_model(
            source="gem",
            created_by_id=test_user.id,
            name=f"S{i}",
            discovery_year=year,
        )
        for i, year in enumerate(years)
    ]
    session.add_all(sources)
    await session.flush()

    resource = ResourceModel.create(created_by=test_user)
    session.add(resource)
    await session.flush()
    session.add_all(
        MembershipModel.create(
            created_by=test_user,
            resource_id=resource.id,
            source=src.source,
            source_pk=src.id,
            status=MembershipStatus.ACTIVE,
        )
        for src in sources
    )
    await session.flush()
    return sources, years


class TestDeterministicTiebreak:
    """Equal/NULL sort values fall back to a deterministic asc(id) tiebreak."""

    @pytest.mark.anyio
    async def test_duplicate_and_null_sort_values(
        self, seeded_integration_session, tiebreak_sources
    ):
        sources, years = tiebreak_sources
        rows, total = await _execute(
            seeded_integration_session,
            sort_by="discovery_year",
            sort_order="asc",
            page_size=200,
        )
        assert total == len(sources)

        # Expected: non-NULL years asc, NULLs last, ties broken by ascending id.
        id_year = list(zip((s.id for s in sources), years))
        expected_ids = [
            id_
            for id_, _ in sorted(
                id_year, key=lambda iy: (iy[1] is None, iy[1] or 0, iy[0])
            )
        ]
        assert [r.id for r in rows] == expected_ids


class TestSortBySource:
    """The source path allows sort_by=source (the resource path forbids it)."""

    @pytest.mark.anyio
    async def test_sort_by_source_orders_by_source(
        self, seeded_integration_session, seeded_sources
    ):
        # sort_by=source is outside the SortableField Literal, so bypass
        # validation via assignment (pydantic does not re-validate on set).
        params = OGFieldQueryParams(page_size=200)
        params.sort_by = "source"
        params.sort_order = "asc"
        rows, total = await source_actions.query(seeded_integration_session, params)
        assert total == 8
        sources_in_order = [r.source for r in rows]
        assert sources_in_order == sorted(sources_in_order)
