"""Integration tests for the v2 read path (og_field_query_view_actions).

The v2 path reads the precomputed ``og_field_resource_query_view`` projection and
must behave identically to ``og_field_resource_actions.query()`` on seeded data,
except for the two documented divergences (``params.source`` ignored; same-key
duplicate source resolved by lowest source_id rather than ``max(value)``).

Window functions + NULLS LAST require SQLite >= 3.30, so the module is guarded.
"""

from __future__ import annotations

import sqlite3

import pytest
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
from stitch.api.entities import User, OGFieldQueryParams
from stitch.ogsi.model.og_field import OilGasFieldBase
from tests.utils import make_source_record


pytestmark = pytest.mark.skipif(
    sqlite3.sqlite_version_info < (3, 30, 0),
    reason="window functions / NULLS LAST need SQLite >= 3.30",
)

_QueryParams = OGFieldQueryParams


async def _create_resource_with_sources(
    session: AsyncSession,
    user: User,
    *source_rows: dict,
    repointed_to: int | None = None,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> int:
    """Seed a ResourceModel + one OilGasFieldSourceModel + MembershipModel per row.

    Adapted from tests/db/test_resource_actions.py::_create_resource_with_sources.
    """
    resource = ResourceModel.create(created_by=user, repointed_to=repointed_to)
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
                status=status,
            )
        )

    await session.flush()
    return resource.id


# ---------------------------------------------------------------------------
# Ported TestResourceQueryAction cases (assert IDENTICAL v2 behavior).
# ---------------------------------------------------------------------------


class TestQueryV2:
    @pytest.fixture
    async def seeded_resources(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Three single-source resources (parallels the reference fixture)."""
        for name in ["Alpha", "Bravo", "Charlie"]:
            await _create_resource_with_sources(
                seeded_integration_session,
                test_user,
                {"source": "rmi", "name": name, "country": "USA"},
            )
        await rebuild_all(seeded_integration_session)

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "params_kwargs, expected_count",
        [
            pytest.param({"page": 1, "page_size": 2}, 2, id="first-page"),
            pytest.param({"page": 2, "page_size": 2}, 1, id="offset-past-partial"),
            pytest.param({"page": 50, "page_size": 10}, 0, id="offset-past-end"),
        ],
    )
    async def test_query_pagination_count_before_pagination(
        self,
        seeded_integration_session: AsyncSession,
        seeded_resources,
        params_kwargs: dict,
        expected_count: int,
    ):
        params = _QueryParams(**params_kwargs)
        items, total = await v2.query_v2(seeded_integration_session, params)
        assert total == 3
        assert len(items) == expected_count

    @pytest.mark.anyio
    async def test_items_have_data_and_provenance(
        self,
        seeded_integration_session: AsyncSession,
        seeded_resources,
    ):
        params = _QueryParams(page=1, page_size=10)
        items, _ = await v2.query_v2(seeded_integration_session, params)
        assert len(items) > 0
        for item in items:
            assert item.id is not None
            assert item.data is not None
            assert isinstance(item.provenance, dict)

    @pytest.mark.anyio
    async def test_priority_coalesced_scalar_fields(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Post-Task-0 priority: rmi > wm > gem > llm (wm beats gem)."""
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": None},
            {
                "source": "gem",
                "name": "GEM Name",
                "country": "CAN",
                "basin": "GEM Basin",
            },
            {
                "source": "wm",
                "name": "WM Name",
                "country": "USA",
                "basin": "WM Basin",
                "reservoir_formation": "WM Formation",
            },
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(page=1, page_size=10)
        items, total = await v2.query_v2(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.name == "RMI Name"
        assert items[0].provenance["name"] == "rmi"
        # country: rmi is None -> next by priority is wm (beats gem post-Task-0)
        assert items[0].data.country == "USA"
        assert items[0].provenance["country"] == "wm"
        assert items[0].data.basin == "WM Basin"
        assert items[0].provenance["basin"] == "wm"
        assert items[0].data.reservoir_formation == "WM Formation"
        assert items[0].provenance["reservoir_formation"] == "wm"

    @pytest.mark.anyio
    async def test_priority_coalesced_owner_operator_lists(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {
                "source": "rmi",
                "name": "RMI Name",
                "country": "USA",
                "owners": [{"name": "RMI Owner", "stake": 55.0}],
                "operators": [{"name": "RMI Operator", "stake": 100.0}],
            },
            {
                "source": "gem",
                "name": "GEM Name",
                "country": "USA",
                "owners": [{"name": "GEM Owner", "stake": 45.0}],
                "operators": [{"name": "GEM Operator", "stake": 100.0}],
            },
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(page=1, page_size=10)
        items, total = await v2.query_v2(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.owners is not None
        assert [(o.name, o.stake) for o in items[0].data.owners] == [
            ("RMI Owner", 55.0)
        ]
        assert items[0].provenance["owners"] == "rmi"
        assert items[0].data.operators is not None
        assert [(o.name, o.stake) for o in items[0].data.operators] == [
            ("RMI Operator", 100.0)
        ]
        assert items[0].provenance["operators"] == "rmi"

    @pytest.mark.anyio
    async def test_null_owner_operator_lists_fall_through(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {
                "source": "rmi",
                "name": "RMI Name",
                "country": "USA",
                "owners": None,
                "operators": None,
            },
            {
                "source": "gem",
                "name": "GEM Name",
                "country": "USA",
                "owners": [{"name": "GEM Owner", "stake": 45.0}],
                "operators": [{"name": "GEM Operator", "stake": 100.0}],
            },
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(page=1, page_size=10)
        items, total = await v2.query_v2(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert [(o.name, o.stake) for o in items[0].data.owners] == [
            ("GEM Owner", 45.0)
        ]
        assert items[0].provenance["owners"] == "gem"
        assert [(o.name, o.stake) for o in items[0].data.operators] == [
            ("GEM Operator", 100.0)
        ]
        assert items[0].provenance["operators"] == "gem"

    @pytest.mark.anyio
    async def test_empty_owner_operator_lists_win(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {
                "source": "rmi",
                "name": "RMI Name",
                "country": "USA",
                "owners": [],
                "operators": [],
            },
            {
                "source": "gem",
                "name": "GEM Name",
                "country": "USA",
                "owners": [{"name": "GEM Owner", "stake": 45.0}],
                "operators": [{"name": "GEM Operator", "stake": 100.0}],
            },
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(page=1, page_size=10)
        items, total = await v2.query_v2(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.owners == []
        assert items[0].provenance["owners"] == "rmi"
        assert items[0].data.operators == []
        assert items[0].provenance["operators"] == "rmi"

    @pytest.mark.anyio
    async def test_licensed_sources_none_returns_all(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "country": "CAN"},
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(page=1, page_size=10)
        items, total = await v2.query_v2(
            seeded_integration_session, params, licensed_sources=None
        )

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.name == "RMI Name"
        assert items[0].provenance["name"] == "rmi"

    @pytest.mark.anyio
    async def test_licensed_sources_empty_returns_null_shells(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "country": "CAN"},
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(page=1, page_size=10)
        items, total = await v2.query_v2(
            seeded_integration_session, params, licensed_sources=frozenset()
        )

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.name is None
        assert items[0].data.country is None
        assert items[0].provenance["name"] is None
        assert items[0].provenance["country"] is None

    @pytest.mark.anyio
    async def test_unlicensed_owner_operator_lists_fall_through(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {
                "source": "rmi",
                "name": "RMI Name",
                "country": "USA",
                "owners": [{"name": "RMI Owner", "stake": 55.0}],
                "operators": [{"name": "RMI Operator", "stake": 100.0}],
            },
            {
                "source": "gem",
                "name": "GEM Name",
                "country": "USA",
                "owners": [{"name": "GEM Owner", "stake": 45.0}],
                "operators": [{"name": "GEM Operator", "stake": 100.0}],
            },
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(page=1, page_size=10)
        items, total = await v2.query_v2(
            seeded_integration_session,
            params,
            licensed_sources=frozenset({"gem", "wm", "llm"}),
        )

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert [(o.name, o.stake) for o in items[0].data.owners] == [
            ("GEM Owner", 45.0)
        ]
        assert items[0].provenance["owners"] == "gem"
        assert [(o.name, o.stake) for o in items[0].data.operators] == [
            ("GEM Operator", 100.0)
        ]
        assert items[0].provenance["operators"] == "gem"

    @pytest.mark.anyio
    async def test_unlicensed_source_falls_through(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "wm", "name": "WoodMac Name", "country": "USA"},
            {"source": "llm", "name": "LLM Name", "country": "USA"},
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(page=1, page_size=10)
        items, total = await v2.query_v2(
            seeded_integration_session,
            params,
            licensed_sources=frozenset({"rmi", "gem", "llm"}),
        )

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.name == "LLM Name"
        assert items[0].provenance["name"] == "llm"

    @pytest.mark.anyio
    async def test_only_unlicensed_source_still_returns_null_shell(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """A resource whose only source is unlicensed survives as a null-shell."""
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {
                "source": "wm",
                "name": "Hidden Name",
                "country": "USA",
                "owners": [{"name": "WM Owner", "stake": 10.0}],
                "operators": [{"name": "WM Op", "stake": 100.0}],
            },
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(page=1, page_size=10)
        items, total = await v2.query_v2(
            seeded_integration_session,
            params,
            licensed_sources=frozenset({"rmi", "gem", "llm"}),
        )

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.name is None
        assert items[0].data.country is None
        assert items[0].data.owners is None
        assert items[0].data.operators is None
        assert items[0].provenance["name"] is None
        assert items[0].provenance["country"] is None
        assert items[0].provenance["owners"] is None
        assert items[0].provenance["operators"] is None

    @pytest.mark.anyio
    async def test_all_null_source_returns_null_shell(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """A resource whose only ACTIVE source has ALL fields None is a null-shell.

        Refresh emits zero projection rows for an all-null source (every field
        hits the None skip), so the resource must enter the v2 universe via its
        membership, not the projection.  query() returns it as total=1, so
        query_v2 must too -- and they must be equal.
        """
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi"},  # all OilGasFieldBase fields default to None
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(page=1, page_size=10)
        items, total = await v2.query_v2(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        # all-None data and all-None provenance
        for field in OilGasFieldBase.model_fields:
            assert getattr(items[0].data, field) is None
            assert items[0].provenance[field] is None

        # Strongest assertion: identical to the reference query().
        ref_items, ref_total = await resource_actions.query(
            seeded_integration_session, params
        )
        assert total == ref_total
        assert [_item_tuple(i) for i in items] == [_item_tuple(i) for i in ref_items]

    @pytest.mark.anyio
    async def test_filters_apply_to_final_coalesced_values_after_licensing(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {
                "source": "rmi",
                "name": "State Test",
                "country": "USA",
                "state_province": "New Mexico",
            },
            {
                "source": "gem",
                "name": "State Test",
                "country": "USA",
                "state_province": "Texas",
            },
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(state_province="Texas", page=1, page_size=10)
        items, total = await v2.query_v2(seeded_integration_session, params)
        assert total == 0
        assert items == []

        items, total = await v2.query_v2(
            seeded_integration_session,
            params,
            licensed_sources=frozenset({"gem", "wm", "llm"}),
        )
        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.state_province == "Texas"
        assert items[0].provenance["state_province"] == "gem"

    @pytest.mark.anyio
    async def test_count_after_coalesced_filter_before_pagination(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "Hidden", "country": "USA"},
            {"source": "gem", "name": "Target Alpha", "country": "USA"},
        )
        await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Target Bravo", "country": "USA"},
        )
        await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Other", "country": "USA"},
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(q="Target", page=1, page_size=1)
        items, total = await v2.query_v2(
            seeded_integration_session,
            params,
            licensed_sources=frozenset({"gem", "wm", "llm"}),
        )

        assert total == 2
        assert len(items) == 1
        assert items[0].data.name == "Target Alpha"

    @pytest.mark.anyio
    async def test_sort_nulls_last_and_id_tiebreak(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        null_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": None, "country": "USA"},
        )
        bravo_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Bravo", "country": "USA"},
        )
        alpha_one_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Alpha", "country": "USA"},
        )
        alpha_two_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Alpha", "country": "USA"},
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(sort_by="name", page=1, page_size=10)
        items, total = await v2.query_v2(seeded_integration_session, params)

        assert total == 4
        assert [item.id for item in items] == [
            alpha_one_id,
            alpha_two_id,
            bravo_id,
            null_id,
        ]

    @pytest.mark.anyio
    async def test_sort_by_year_field(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        old_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Old", "country": "USA", "discovery_year": 1950},
        )
        new_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "New", "country": "USA", "discovery_year": 2010},
        )
        none_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "NoYear", "country": "USA"},
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(
            sort_by="discovery_year", sort_order="asc", page=1, page_size=10
        )
        items, total = await v2.query_v2(seeded_integration_session, params)

        assert total == 3
        assert [item.id for item in items] == [old_id, new_id, none_id]
        # year coerced to int (not float) on hydrate
        assert items[0].data.discovery_year == 1950
        assert isinstance(items[0].data.discovery_year, int)

    @pytest.mark.anyio
    async def test_repointed_and_inactive_excluded(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        root_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Root", "country": "USA"},
        )
        await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Repointed", "country": "USA"},
            repointed_to=root_id,
        )
        await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Inactive", "country": "USA"},
            status=MembershipStatus.INACTIVE,
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(page=1, page_size=10)
        items, total = await v2.query_v2(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [root_id]

    @pytest.mark.anyio
    async def test_id_filter_targets_resource_id_directly(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        target_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "Target", "country": "USA"},
        )
        await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "Other", "country": "USA"},
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(id=target_id, page=1, page_size=10)
        items, total = await v2.query_v2(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [target_id]
        assert items[0].data.name == "Target"


# ---------------------------------------------------------------------------
# Documented divergences from query().
# ---------------------------------------------------------------------------


class TestQueryV2Divergences:
    @pytest.mark.anyio
    async def test_params_source_is_ignored(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """v2 ignores params.source entirely; only licensed_sources filters."""
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "country": "USA"},
        )
        await rebuild_all(seeded_integration_session)

        # Narrowing source to gem would, under query(), surface GEM Name.
        # v2 ignores it -> rmi still wins by priority.
        params = _QueryParams(source=["gem"], page=1, page_size=10)
        items, total = await v2.query_v2(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.name == "RMI Name"
        assert items[0].provenance["name"] == "rmi"

    @pytest.mark.anyio
    async def test_same_key_duplicate_source_lowest_source_id_wins(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Two ACTIVE memberships of the SAME source key: v2 picks lowest source_id.

        NOTE: this intentionally diverges from query(), which uses max(value).
        """
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            # both gem; first-created has the lower source_id (auto-increment PK)
            {"source": "gem", "name": "AAA First", "country": "USA"},
            {"source": "gem", "name": "ZZZ Second", "country": "USA"},
        )
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(page=1, page_size=10)
        items, total = await v2.query_v2(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        # lowest source_id wins (the first-created "AAA First"),
        # NOT max(value) which would be "ZZZ Second".
        assert items[0].data.name == "AAA First"


# ---------------------------------------------------------------------------
# Equivalence harness: query_v2 == query on the same seeded DB.
# ---------------------------------------------------------------------------


async def _seed_varied_db(session: AsyncSession, user: User) -> None:
    """A varied DB exercising priority, licensing, nulls, lists, years, repointed."""
    # multi-source, full field coverage
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
            "discovery_year": 1948,
            "production_start_year": 1951,
            "latitude": 25.4,
            "longitude": 49.6,
            "owners": [{"name": "Aramco", "stake": 100.0}],
            "operators": [{"name": "Aramco Ops", "stake": 100.0}],
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
            "reservoir_formation": "Arab-D",
        },
    )
    # rmi has null country -> falls through to wm (post-Task-0)
    await _create_resource_with_sources(
        session,
        user,
        {"source": "rmi", "name": "Burgan", "country": None, "discovery_year": 1938},
        {"source": "wm", "name": "Burgan WM", "country": "KWT", "fid_year": 1946},
        {"source": "gem", "name": "Burgan GEM", "country": "IRQ"},
    )
    # only unlicensed-ish (wm/llm) source
    await _create_resource_with_sources(
        session,
        user,
        {"source": "wm", "name": "Safaniya", "country": "SAU", "latitude": 28.0},
        {"source": "llm", "name": "Safaniya LLM", "country": "SAU"},
    )
    # null name (sorts last)
    await _create_resource_with_sources(
        session,
        user,
        {"source": "gem", "name": None, "country": "USA", "discovery_year": 2001},
    )
    # duplicate name for id-tiebreak under name sort
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
    # empty-list owners win over a lower-priority list
    await _create_resource_with_sources(
        session,
        user,
        {"source": "rmi", "name": "EmptyOwners", "country": "USA", "owners": []},
        {
            "source": "gem",
            "name": "EmptyOwners GEM",
            "country": "USA",
            "owners": [{"name": "GEM Owner", "stake": 50.0}],
        },
    )
    # repointed (excluded) + inactive (excluded)
    root_id = await _create_resource_with_sources(
        session, user, {"source": "gem", "name": "Root", "country": "USA"}
    )
    await _create_resource_with_sources(
        session,
        user,
        {"source": "gem", "name": "Repointed", "country": "USA"},
        repointed_to=root_id,
    )
    await _create_resource_with_sources(
        session,
        user,
        {"source": "gem", "name": "InactiveOnly", "country": "USA"},
        status=MembershipStatus.INACTIVE,
    )


def _item_tuple(item):
    """Comparable representation: id, data dict, provenance dict."""
    return (item.id, item.data.model_dump(mode="json"), item.provenance)


# matrix of query params (source kept at default; v2 ignores it)
_PARAM_MATRIX = [
    pytest.param({"page": 1, "page_size": 50}, id="plain"),
    pytest.param({"q": "Ghawar", "page": 1, "page_size": 50}, id="q-search"),
    pytest.param({"q": "Basin", "page": 1, "page_size": 50}, id="q-search-coalesced"),
    pytest.param({"country": "SAU", "page": 1, "page_size": 50}, id="filter-country"),
    pytest.param({"name": "Alpha", "page": 1, "page_size": 50}, id="filter-name"),
    pytest.param(
        {"basin": "Arabian Basin WM", "page": 1, "page_size": 50}, id="filter-basin"
    ),
    pytest.param({"id": 1, "page": 1, "page_size": 50}, id="filter-id"),
    pytest.param(
        {"sort_by": "name", "sort_order": "asc", "page": 1, "page_size": 50},
        id="sort-name-asc",
    ),
    pytest.param(
        {"sort_by": "name", "sort_order": "desc", "page": 1, "page_size": 50},
        id="sort-name-desc",
    ),
    pytest.param(
        {"sort_by": "discovery_year", "sort_order": "asc", "page": 1, "page_size": 50},
        id="sort-year-asc",
    ),
    pytest.param(
        {"sort_by": "discovery_year", "sort_order": "desc", "page": 1, "page_size": 50},
        id="sort-year-desc",
    ),
    pytest.param({"page": 1, "page_size": 2}, id="page-1"),
    pytest.param({"page": 2, "page_size": 2}, id="page-2"),
    pytest.param({"page": 50, "page_size": 2}, id="deep-page"),
]

_LICENSE_MATRIX = [
    pytest.param(None, id="lic-none"),
    pytest.param(frozenset(), id="lic-empty"),
    pytest.param(frozenset({"rmi"}), id="lic-rmi"),
    pytest.param(frozenset({"gem", "wm", "llm"}), id="lic-gem-wm-llm"),
]


class TestQueryV2Equivalence:
    @pytest.mark.anyio
    @pytest.mark.parametrize("params_kwargs", _PARAM_MATRIX)
    @pytest.mark.parametrize("licensed", _LICENSE_MATRIX)
    async def test_query_v2_matches_query(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        params_kwargs: dict,
        licensed,
    ):
        await _seed_varied_db(seeded_integration_session, test_user)
        await rebuild_all(seeded_integration_session)

        params = _QueryParams(**params_kwargs)

        v2_items, v2_total = await v2.query_v2(
            seeded_integration_session, params, licensed_sources=licensed
        )
        ref_items, ref_total = await resource_actions.query(
            seeded_integration_session, params, licensed_sources=licensed
        )

        assert v2_total == ref_total
        assert [i.id for i in v2_items] == [i.id for i in ref_items]
        assert [_item_tuple(i) for i in v2_items] == [_item_tuple(i) for i in ref_items]
