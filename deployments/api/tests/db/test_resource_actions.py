"""Database integration tests for domain-agnostic resource_actions."""

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db import utils
from stitch.api.db.errors import InvalidActionError, ResourceIntegrityError
from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    OGFieldResourceSourcePriority,
    OilGasFieldSourceValueModel,
    ResourceModel,
)
from stitch.api.entities import (
    OGFieldFilterOptionsParams,
    OGFieldQueryParams,
    User,
)
from tests.factories import ResourceCreateFactory
from tests.utils import make_source_model


_QueryParams = OGFieldQueryParams


async def _create_resource_with_sources(
    session: AsyncSession,
    user: User,
    *source_rows: dict,
    repointed_to: int | None = None,
) -> int:
    resource = ResourceModel.create(created_by=user, repointed_to=repointed_to)
    session.add(resource)
    await session.flush()

    for row in source_rows:
        attrs = {k: v for k, v in row.items() if k != "source"}
        source = make_source_model(
            source=row["source"],
            created_by_id=user.id,
            **attrs,
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

    await session.flush()
    return resource.id


async def _add_source(session, user, rid: int, **attrs) -> int:
    """Attach one active source record (with values) to an existing resource."""
    source = make_source_model(
        source=attrs.pop("source"), created_by_id=user.id, **attrs
    )
    session.add(source)
    await session.flush()
    session.add(
        MembershipModel.create(
            created_by=user,
            resource_id=rid,
            source=source.source,
            source_pk=source.id,
            status=MembershipStatus.ACTIVE,
        )
    )
    await session.flush()
    return source.id


async def _source_pks(session, rid: int, source_key: str) -> list[int]:
    """Active source-record ids for one source of a resource, ascending by id."""
    stmt = (
        select(MembershipModel.source_pk)
        .where(
            MembershipModel.resource_id == rid,
            MembershipModel.source == source_key,
        )
        .order_by(MembershipModel.source_pk)
    )
    return list((await session.scalars(stmt)).all())


async def _override(
    session, user, rid: int, source_key: str, field: str, priority: int
):
    """Insert one per-field override row for the (single) record of a source."""
    (pk,) = await _source_pks(session, rid, source_key)
    session.add(
        OGFieldResourceSourcePriority.create(
            created_by=user,
            resource_id=rid,
            source=source_key,
            source_pk=pk,
            colname=field,
            priority=priority,
        )
    )
    await session.flush()
    return pk


class TestCreateResourceActionIntegration:
    """Integration tests for resource_actions.create() with real database."""

    @pytest.mark.anyio
    async def test_creates_resource_with_minimal_payload(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        og_create_res_fact: ResourceCreateFactory,
    ):
        resource_in = og_create_res_fact()

        result = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=resource_in,
        )

        assert result.id is not None

        db_resource = await seeded_integration_session.get(ResourceModel, result.id)
        assert db_resource is not None

    @pytest.mark.anyio
    async def test_creates_resource_with_label(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        og_create_res_fact: ResourceCreateFactory,
    ):
        resource_in = og_create_res_fact(name="Test Label")

        result = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=resource_in,
        )

        assert result.id is not None
        assert result.view is not None
        assert result.view.name == "Test Label"

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
        og_create_res_fact: ResourceCreateFactory,
    ):
        res = og_create_res_fact(name="Get Test")
        created = await resource_actions.create(
            session=seeded_integration_session,
            user=test_user,
            resource=res,
        )

        result = await resource_actions.get(
            session=seeded_integration_session,
            id=created.id,
        )

        assert result.id == created.id
        assert result.view is not None
        assert result.view.name == "Get Test"

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


class TestResourceQueryAction:
    """Integration tests for resource_actions.query() and count()."""

    @pytest.fixture
    async def seeded_resources(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        og_create_res_fact: ResourceCreateFactory,
    ):
        """Create 3 resources for query tests."""
        for name in ["Alpha", "Bravo", "Charlie"]:
            await resource_actions.create(
                session=seeded_integration_session,
                user=test_user,
                resource=og_create_res_fact(name=name),
            )

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "params_kwargs, expected_count",
        [
            pytest.param(
                {"page": 1, "page_size": 2},
                2,
                id="first-page",
            ),
            pytest.param(
                {"page": 2, "page_size": 2},
                1,
                id="offset-past-partial",
            ),
            pytest.param(
                {"page": 50, "page_size": 10},
                0,
                id="offset-past-end",
            ),
        ],
    )
    async def test_query_pagination(
        self,
        seeded_integration_session: AsyncSession,
        seeded_resources,
        params_kwargs: dict,
        expected_count: int,
    ):
        params = _QueryParams(**params_kwargs)
        items, total = await resource_actions.query(seeded_integration_session, params)
        assert total == 3
        assert len(items) == expected_count

    @pytest.mark.anyio
    async def test_items_have_data_and_provenance(
        self,
        seeded_integration_session: AsyncSession,
        seeded_resources,
    ):
        """List items include coalesced data and provenance dict."""
        params = _QueryParams(page=1, page_size=10)
        items, _ = await resource_actions.query(seeded_integration_session, params)
        assert len(items) > 0
        for item in items:
            assert item.id is not None
            assert item.data is not None
            assert isinstance(item.provenance, dict)

    @pytest.mark.anyio
    async def test_source_param_is_ignored_resources_not_source_gated(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """``params.source`` is ignored: resources are not source-gated.

        The universe is membership-derived (only licensing narrows it), so a
        ``source=['gem']`` filter does not exclude resources lacking a gem
        membership, and coalescing still resolves the full-priority winner.
        """
        included_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "country": "USA"},
        )
        only_rmi_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "Only RMI", "country": "USA"},
        )

        params = _QueryParams(source=["gem"], page=1, page_size=10)
        items, total = await resource_actions.query(seeded_integration_session, params)

        # Both resources appear -- source is not a resource-level filter.
        assert total == 2
        assert {item.id for item in items} == {included_id, only_rmi_id}

        # The rmi+gem resource still coalesces the rmi-priority winner.
        included = next(item for item in items if item.id == included_id)
        assert included.data.name == "RMI Name"
        assert included.provenance["name"] == "rmi"

    @pytest.mark.anyio
    async def test_no_redaction_uses_priority_coalesced_scalar_fields(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
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

        params = _QueryParams(page=1, page_size=10)
        items, total = await resource_actions.query(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.name == "RMI Name"
        assert items[0].provenance["name"] == "rmi"
        assert items[0].data.country == "USA"
        assert items[0].provenance["country"] == "wm"
        assert items[0].data.basin == "WM Basin"
        assert items[0].provenance["basin"] == "wm"
        assert items[0].data.reservoir_formation == "WM Formation"
        assert items[0].provenance["reservoir_formation"] == "wm"

    @pytest.mark.anyio
    async def test_empty_string_value_loses_to_lower_priority_nonempty(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        # Highest-priority source (rmi) supplies an empty-string basin. It is
        # dropped on write (empty == unset), so it never becomes a value row and
        # coalescing falls through to the lower-priority non-empty value.
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA", "basin": ""},
            {
                "source": "gem",
                "name": "GEM Name",
                "country": "USA",
                "basin": "GEM Basin",
            },
        )

        params = _QueryParams(page=1, page_size=10)
        items, total = await resource_actions.query(seeded_integration_session, params)

        assert total == 1
        assert items[0].data.basin == "GEM Basin"
        assert items[0].provenance["basin"] == "gem"

        # The empty value was never persisted, so the all-sources view lists
        # only gem and its winner-first order agrees with the coalesced winner.
        values = await resource_actions.field_source_values(
            seeded_integration_session, resource_id, "basin"
        )
        assert [v.source for v in values] == ["gem"]

    @pytest.mark.anyio
    async def test_empty_string_value_row_rejected_by_db_constraint(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        # Defense in depth: even if a caller bypasses the write-path skip, the
        # DB refuses to persist an empty-string value row.
        source = make_source_model(
            source="rmi", created_by_id=test_user.id, name="RMI Name"
        )
        seeded_integration_session.add(source)
        await seeded_integration_session.flush()

        empty = OilGasFieldSourceValueModel.from_attribute("basin", "")
        empty.source_pk = source.id
        seeded_integration_session.add(empty)

        with pytest.raises(IntegrityError):
            await seeded_integration_session.flush()
        await seeded_integration_session.rollback()

    @pytest.mark.anyio
    async def test_no_redaction_uses_priority_coalesced_owner_operator_lists(
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

        params = _QueryParams(page=1, page_size=10)
        items, total = await resource_actions.query(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.owners is not None
        assert [(owner.name, owner.stake) for owner in items[0].data.owners] == [
            ("RMI Owner", 55.0)
        ]
        assert items[0].provenance["owners"] == "rmi"
        assert items[0].data.operators is not None
        assert [
            (operator.name, operator.stake) for operator in items[0].data.operators
        ] == [("RMI Operator", 100.0)]
        assert items[0].provenance["operators"] == "rmi"

    @pytest.mark.anyio
    async def test_null_owner_operator_lists_fall_through_to_lower_priority_source(
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

        params = _QueryParams(page=1, page_size=10)
        items, total = await resource_actions.query(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.owners is not None
        assert [(owner.name, owner.stake) for owner in items[0].data.owners] == [
            ("GEM Owner", 45.0)
        ]
        assert items[0].provenance["owners"] == "gem"
        assert items[0].data.operators is not None
        assert [
            (operator.name, operator.stake) for operator in items[0].data.operators
        ] == [("GEM Operator", 100.0)]
        assert items[0].provenance["operators"] == "gem"

    @pytest.mark.anyio
    async def test_empty_owner_operator_lists_win_over_lower_priority_values(
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

        params = _QueryParams(page=1, page_size=10)
        items, total = await resource_actions.query(seeded_integration_session, params)

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
        """``licensed_sources=None`` must be a no-op preserving every membership."""
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "country": "CAN"},
        )

        params = _QueryParams(page=1, page_size=10)
        items, total = await resource_actions.query(
            seeded_integration_session, params, licensed_sources=None
        )

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.name == "RMI Name"
        assert items[0].provenance["name"] == "rmi"

    @pytest.mark.anyio
    async def test_unlicensed_owner_operator_lists_fall_through_to_lower_priority_source(
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

        params = _QueryParams(page=1, page_size=10)
        items, total = await resource_actions.query(
            seeded_integration_session,
            params,
            licensed_sources=frozenset({"gem", "wm", "llm"}),
        )

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.owners is not None
        assert [(owner.name, owner.stake) for owner in items[0].data.owners] == [
            ("GEM Owner", 45.0)
        ]
        assert items[0].provenance["owners"] == "gem"
        assert items[0].data.operators is not None
        assert [
            (operator.name, operator.stake) for operator in items[0].data.operators
        ] == [("GEM Operator", 100.0)]
        assert items[0].provenance["operators"] == "gem"

    @pytest.mark.anyio
    async def test_unlicensed_source_falls_through_to_lower_priority_source(
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

        params = _QueryParams(page=1, page_size=10)
        items, total = await resource_actions.query(
            seeded_integration_session,
            params,
            licensed_sources=frozenset({"rmi", "gem", "llm"}),
        )

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.name == "LLM Name"
        assert items[0].provenance["name"] == "llm"


class TestResourceUniverseAndNarrowing:
    """Membership-derived universe, source-ignoring, and pivot-narrowing proofs."""

    @pytest.mark.anyio
    async def test_source_param_ignored_across_multiple_keys(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """``params.source`` never narrows the resource universe, any key(s)."""
        gem_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Gem", "country": "USA"},
        )
        wm_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "wm", "name": "WM", "country": "USA"},
        )
        rmi_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "RMI", "country": "USA"},
        )

        # A source filter naming a key none of them have still returns all three.
        params = _QueryParams(source=["llm"], page=1, page_size=10)
        items, total = await resource_actions.query(seeded_integration_session, params)
        assert total == 3
        assert {item.id for item in items} == {gem_id, wm_id, rmi_id}

        # An explicit subset is equally ignored.
        params = _QueryParams(source=["gem"], page=1, page_size=10)
        _, total = await resource_actions.query(seeded_integration_session, params)
        assert total == 3

    @pytest.mark.anyio
    async def test_all_null_source_resource_appears_as_null_shell(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """A resource whose only source has all-null attributes still appears.

        It emits zero coalesced rows but is membership-derived, so it is counted
        and hydrated as a null-shell.
        """
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem"},
        )

        params = _QueryParams(page=1, page_size=10)
        items, total = await resource_actions.query(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.name is None
        assert items[0].data.country is None
        assert items[0].provenance["name"] is None

    @pytest.mark.anyio
    async def test_filter_by_basin_narrows(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """basin filter proves basin is pivoted and filtered on coalesced values."""
        permian_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "A", "country": "USA", "basin": "Permian"},
        )
        await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "B", "country": "USA", "basin": "Neuquen"},
        )

        params = _QueryParams(basin="Permian", page=1, page_size=10)
        items, total = await resource_actions.query(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [permian_id]
        assert items[0].data.basin == "Permian"

    @pytest.mark.anyio
    async def test_sort_by_discovery_year_numeric_nulls_last(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """discovery_year sorts numerically (from value_num) with NULLs last."""
        y2000 = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "C", "country": "USA", "discovery_year": 2000},
        )
        y1990 = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "A", "country": "USA", "discovery_year": 1990},
        )
        ynull = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "B", "country": "USA"},
        )

        params = _QueryParams(
            sort_by="discovery_year", sort_order="asc", page=1, page_size=10
        )
        items, total = await resource_actions.query(seeded_integration_session, params)

        assert total == 3
        assert [item.id for item in items] == [y1990, y2000, ynull]
        assert [item.data.discovery_year for item in items] == [1990, 2000, None]

    @pytest.mark.anyio
    async def test_empty_involved_returns_all_active_ordered_by_id(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """sort_by=id, no q/filters: no pivot at all, all active resources by id."""
        ids = [
            await _create_resource_with_sources(
                seeded_integration_session,
                test_user,
                {"source": "gem", "name": name, "country": "USA"},
            )
            for name in ["Zeta", "Alpha", "Mu"]
        ]

        params = _QueryParams(sort_by="id", page=1, page_size=10)
        items, total = await resource_actions.query(seeded_integration_session, params)

        assert total == 3
        assert [item.id for item in items] == sorted(ids)

    @pytest.mark.anyio
    async def test_sort_by_id_and_resource_id_honor_sort_order(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """On resources, both id and resource_id are real id-sorts with direction."""
        ids = [
            await _create_resource_with_sources(
                seeded_integration_session,
                test_user,
                {"source": "gem", "name": name, "country": "USA"},
            )
            for name in ["A", "B", "C"]
        ]
        ascending = sorted(ids)

        items, _ = await resource_actions.query(
            seeded_integration_session,
            _QueryParams(sort_by="id", sort_order="desc", page_size=10),
        )
        assert [i.id for i in items] == list(reversed(ascending))

        items, _ = await resource_actions.query(
            seeded_integration_session,
            _QueryParams(sort_by="resource_id", sort_order="asc", page_size=10),
        )
        assert [i.id for i in items] == ascending

        items, _ = await resource_actions.query(
            seeded_integration_session,
            _QueryParams(sort_by="resource_id", sort_order="desc", page_size=10),
        )
        assert [i.id for i in items] == list(reversed(ascending))

    @pytest.mark.anyio
    async def test_query_hydration_round_trips_constant_in_page_size(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """query hydrates in constant round-trips, independent of page size (no N+1)."""
        for name in ["A", "B", "C", "D"]:
            await _create_resource_with_sources(
                seeded_integration_session,
                test_user,
                {"source": "gem", "name": name, "country": "USA"},
            )
        sync_engine = seeded_integration_session.bind.sync_engine

        async def _count(page_size):
            executions = 0

            def _inc(conn, cursor, statement, parameters, context, executemany):
                nonlocal executions
                executions += 1

            event.listen(sync_engine, "before_cursor_execute", _inc)
            try:
                items, _ = await resource_actions.query(
                    seeded_integration_session,
                    _QueryParams(page=1, page_size=page_size),
                )
            finally:
                event.remove(sync_engine, "before_cursor_execute", _inc)
            return executions, items

        one_count, _ = await _count(1)
        all_count, all_items = await _count(10)

        # No N+1: a 4-row page costs the same round-trips as a 1-row page.
        assert one_count == all_count
        # Small constant: ids + count + source/priority join + selectin values.
        assert all_count <= 5
        assert len(all_items) == 4


class TestResourceFilterOptionsAction:
    """Integration tests for resource_actions.filter_options()."""

    @pytest.mark.anyio
    async def test_returns_distinct_sorted_coalesced_values(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
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

        values = await resource_actions.filter_options(
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

        values = await resource_actions.filter_options(
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

        values = await resource_actions.filter_options(
            seeded_integration_session,
            OGFieldFilterOptionsParams(field="country"),
        )

        assert values == ["USA"]

    def test_postgres_distinct_query_orders_by_selected_value_alias(self):
        """The rewritten filter_options construction compiles on Postgres.

        Mirrors ``filter_options``: distinct over the coalesced value column for
        one field, ordered by the selected alias.
        """
        params = OGFieldFilterOptionsParams(field="basin")
        base_cte = resource_actions.construct_base_query_statement(
            licensed_sources=frozenset({"gem", "wm", "rmi", "llm"}),
        )
        filtered = (
            resource_actions.select(base_cte)
            .where(base_cte.c.colname == params.field)
            .cte()
        )
        ranked = resource_actions.add_ranking(filtered).cte("ranked")
        value_col = getattr(ranked.c, resource_actions.value_attr_for(params.field))
        labeled = value_col.label("value")
        stmt = (
            resource_actions.select(labeled)
            .where(value_col.is_not(None), value_col != "")
            .distinct()
            .order_by(labeled)
        )

        sql = str(
            stmt.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )

        assert "SELECT DISTINCT ranked.value_text AS value" in sql
        assert "ORDER BY value" in sql

    @pytest.mark.anyio
    async def test_only_unlicensed_selected_sources_still_return_resource(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "wm", "name": "Hidden Name", "country": "USA"},
        )

        params = _QueryParams(page=1, page_size=10)
        items, total = await resource_actions.query(
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

        params = _QueryParams(state_province="Texas", page=1, page_size=10)
        items, total = await resource_actions.query(seeded_integration_session, params)

        assert total == 0
        assert items == []

        items, total = await resource_actions.query(
            seeded_integration_session,
            params,
            licensed_sources=frozenset({"gem", "wm", "llm"}),
        )

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.state_province == "Texas"
        assert items[0].provenance["state_province"] == "gem"

    @pytest.mark.anyio
    async def test_count_is_after_licensed_coalesced_filter_before_pagination(
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

        params = _QueryParams(q="Target", page=1, page_size=1)
        items, total = await resource_actions.query(
            seeded_integration_session,
            params,
            licensed_sources=frozenset({"gem", "wm", "llm"}),
        )

        assert total == 2
        assert len(items) == 1
        assert items[0].data.name == "Target Alpha"

    @pytest.mark.anyio
    async def test_sort_uses_final_values_nulls_last_and_id_tiebreak(
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

        params = _QueryParams(sort_by="name", page=1, page_size=10)
        items, total = await resource_actions.query(seeded_integration_session, params)

        assert total == 4
        assert [item.id for item in items] == [
            alpha_one_id,
            alpha_two_id,
            bravo_id,
            null_id,
        ]

    @pytest.mark.anyio
    async def test_repointed_resources_are_excluded(
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

        params = _QueryParams(page=1, page_size=10)
        items, total = await resource_actions.query(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [root_id]


class TestResourcePriorityOverride:
    """A per-field override re-ranks sources, flipping the coalesced winner."""

    async def _seed(self, session, user) -> int:
        # Default priority: wm(2) outranks gem(4), so wm wins by default.
        return await _create_resource_with_sources(
            session,
            user,
            {"source": "gem", "name": "GEM Name", "country": "USA"},
            {"source": "wm", "name": "WM Name", "country": "CAN"},
        )

    @pytest.mark.anyio
    async def test_override_flips_winner_in_detail_and_list(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        session = seeded_integration_session
        rid = await self._seed(session, test_user)

        # Default: wm wins.
        before = await resource_actions.get(session, rid)
        assert before.view.name == "WM Name"
        assert before.provenance["name"][1] == "wm"

        # Override gem to top priority for the NAME field of THIS resource only.
        await _override(session, test_user, rid, "gem", "name", priority=0)

        # Detail path reflects the override on name (value + provenance)...
        after = await resource_actions.get(session, rid)
        assert after.view.name == "GEM Name"
        assert after.provenance["name"][1] == "gem"
        # ...but country is a different field with no override, so it still
        # coalesces to wm -- overrides are per-field.
        assert after.view.country == "CAN"
        assert after.provenance["country"][1] == "wm"

        # List path reflects it too.
        items, _ = await resource_actions.query(session, _QueryParams())
        item = next(i for i in items if i.id == rid)
        assert item.data.name == "GEM Name"
        assert item.provenance["name"] == "gem"

    @pytest.mark.anyio
    async def test_override_is_scoped_to_its_resource(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        session = seeded_integration_session
        overridden = await self._seed(session, test_user)
        untouched = await self._seed(session, test_user)

        await _override(session, test_user, overridden, "gem", "name", priority=0)

        assert (await resource_actions.get(session, overridden)).view.name == "GEM Name"
        # The other resource keeps the default ranking.
        assert (await resource_actions.get(session, untouched)).view.name == "WM Name"


class TestFieldSourceValues:
    """Per-field source-value listing, best-priority first."""

    async def _seed(self, session, user) -> int:
        # wm(2) outranks gem(4) by default; llm has no state_province.
        return await _create_resource_with_sources(
            session,
            user,
            {"source": "gem", "name": "GEM Name", "country": "USA", "basin": "Alpha"},
            {"source": "wm", "name": "WM Name", "country": "CAN", "basin": "Beta"},
            {"source": "llm", "name": "LLM Name", "country": "GBR"},
        )

    @pytest.mark.anyio
    async def test_lists_values_sorted_by_priority_with_winner_first(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        session = seeded_integration_session
        rid = await self._seed(session, test_user)

        rows = await resource_actions.field_source_values(session, rid, "name")

        # wm(2) < gem(4) < llm(5): winner (wm) first, then in priority order.
        assert [(r.source, r.value) for r in rows] == [
            ("wm", "WM Name"),
            ("gem", "GEM Name"),
            ("llm", "LLM Name"),
        ]
        assert [r.priority for r in rows] == sorted(r.priority for r in rows)

    @pytest.mark.anyio
    async def test_override_reorders_field_values(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        session = seeded_integration_session
        rid = await self._seed(session, test_user)
        await _override(session, test_user, rid, "gem", "basin", priority=0)

        rows = await resource_actions.field_source_values(session, rid, "basin")

        # gem promoted above wm; llm has no basin so it is omitted.
        assert [(r.source, r.value) for r in rows] == [
            ("gem", "Alpha"),
            ("wm", "Beta"),
        ]
        # The curated row is flagged; the untouched one is not.
        assert [r.is_override for r in rows] == [True, False]
        # Priority is the 0-based rank position, winner first.
        assert [r.priority for r in rows] == [0, 1]

    @pytest.mark.anyio
    async def test_omits_sources_without_a_value(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        session = seeded_integration_session
        rid = await self._seed(session, test_user)

        rows = await resource_actions.field_source_values(
            session, rid, "state_province"
        )

        assert rows == []

    @pytest.mark.anyio
    async def test_unlicensed_sources_are_excluded(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        session = seeded_integration_session
        rid = await self._seed(session, test_user)

        rows = await resource_actions.field_source_values(
            session, rid, "name", licensed_sources=["gem"]
        )

        assert [r.source for r in rows] == ["gem"]

    @pytest.mark.anyio
    async def test_unknown_field_is_rejected(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        session = seeded_integration_session
        rid = await self._seed(session, test_user)

        with pytest.raises(HTTPException) as exc:
            await resource_actions.field_source_values(session, rid, "not_a_field")
        assert exc.value.status_code == 422

    @pytest.mark.anyio
    async def test_missing_resource_is_404(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        with pytest.raises(HTTPException) as exc:
            await resource_actions.field_source_values(
                seeded_integration_session, 9_999_999, "name"
            )
        assert exc.value.status_code == 404


class TestSetFieldSourcePriority:
    """Write path: persist and enforce a curator's per-field source ordering."""

    async def _seed(self, session, user) -> int:
        # gem(2) wins name & basin by default; wm(3) is second.
        return await _create_resource_with_sources(
            session,
            user,
            {"source": "gem", "name": "GEM Name", "basin": "Alpha"},
            {"source": "wm", "name": "WM Name", "basin": "Beta"},
        )

    @pytest.mark.anyio
    async def test_reorder_flips_winner_detail_and_list(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        rid = await self._seed(session, test_user)
        (gem_pk,) = await _source_pks(session, rid, "gem")
        (wm_pk,) = await _source_pks(session, rid, "wm")

        result = await resource_actions.set_field_source_priority(
            session, test_user, rid, "name", [wm_pk, gem_pk]
        )

        # Returned ranking is winner-first and flags the curated rows.
        assert [(r.source, r.source_id) for r in result] == [
            ("wm", wm_pk),
            ("gem", gem_pk),
        ]
        assert all(r.is_override for r in result)

        # Detail and list agree on the new coalesced winner.
        detail = await resource_actions.get(session, rid)
        assert detail.view.name == "WM Name"
        items, _ = await resource_actions.query(session, _QueryParams())
        assert next(i for i in items if i.id == rid).data.name == "WM Name"

        # basin was not curated -> still gem by default (per-field isolation).
        assert detail.view.basin == "Alpha"

    @pytest.mark.anyio
    async def test_noop_when_order_unchanged_writes_nothing(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        rid = await self._seed(session, test_user)
        (gem_pk,) = await _source_pks(session, rid, "gem")
        (wm_pk,) = await _source_pks(session, rid, "wm")

        # gem, wm is already the default order -> no-op, no rows written.
        await resource_actions.set_field_source_priority(
            session, test_user, rid, "name", [gem_pk, wm_pk]
        )

        count = await session.scalar(
            select(func.count()).select_from(OGFieldResourceSourcePriority)
        )
        assert count == 0

    @pytest.mark.anyio
    async def test_duplicate_pks_rejected(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        rid = await self._seed(session, test_user)
        (wm_pk,) = await _source_pks(session, rid, "wm")
        with pytest.raises(InvalidActionError):
            await resource_actions.set_field_source_priority(
                session, test_user, rid, "name", [wm_pk, wm_pk]
            )

    @pytest.mark.anyio
    async def test_incomplete_set_rejected(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        rid = await self._seed(session, test_user)
        (wm_pk,) = await _source_pks(session, rid, "wm")
        with pytest.raises(InvalidActionError):
            # gem omitted.
            await resource_actions.set_field_source_priority(
                session, test_user, rid, "name", [wm_pk]
            )

    @pytest.mark.anyio
    async def test_extra_pk_rejected(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        rid = await self._seed(session, test_user)
        (gem_pk,) = await _source_pks(session, rid, "gem")
        (wm_pk,) = await _source_pks(session, rid, "wm")
        with pytest.raises(InvalidActionError):
            await resource_actions.set_field_source_priority(
                session, test_user, rid, "name", [wm_pk, gem_pk, 9_999_999]
            )

    @pytest.mark.anyio
    async def test_unknown_field_rejected(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        rid = await self._seed(session, test_user)
        with pytest.raises(HTTPException) as exc:
            await resource_actions.set_field_source_priority(
                session, test_user, rid, "not_a_field", []
            )
        assert exc.value.status_code == 422

    @pytest.mark.anyio
    async def test_missing_resource_is_404(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        with pytest.raises(HTTPException) as exc:
            await resource_actions.set_field_source_priority(
                seeded_integration_session, test_user, 9_999_999, "name", []
            )
        assert exc.value.status_code == 404

    @pytest.mark.anyio
    async def test_repointed_resource_rejected(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        base = await self._seed(session, test_user)
        repointed = await _create_resource_with_sources(
            session,
            test_user,
            {"source": "gem", "name": "X"},
            repointed_to=base,
        )
        with pytest.raises(ResourceIntegrityError):
            await resource_actions.set_field_source_priority(
                session, test_user, repointed, "name", []
            )

    @pytest.mark.anyio
    async def test_new_source_ranks_last_after_curation(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        rid = await self._seed(session, test_user)
        (gem_pk,) = await _source_pks(session, rid, "gem")
        (wm_pk,) = await _source_pks(session, rid, "wm")

        await resource_actions.set_field_source_priority(
            session, test_user, rid, "name", [wm_pk, gem_pk]
        )

        # A source added AFTER curation has no override row for the field, so it
        # lands in the default tier and ranks last -- even though rmi has the best
        # global default priority (1).
        rmi_pk = await _add_source(
            session, test_user, rid, source="rmi", name="RMI Name"
        )

        rows = await resource_actions.field_source_values(session, rid, "name")
        assert [(r.source, r.source_id) for r in rows] == [
            ("wm", wm_pk),
            ("gem", gem_pk),
            ("rmi", rmi_pk),
        ]
        # The coalesced winner is still the curated wm, not the newer rmi.
        assert (await resource_actions.get(session, rid)).view.name == "WM Name"


class TestResourceDetailCoalescing:
    """Detail-path (``resource_actions.get``) coalescing behavior.

    Characterizes the per-resource detail contract so it survives the move from
    the SQL window-function CTE to in-memory coalescing over already-loaded
    source data. Provenance on the detail path is the ``(value, source,
    source_pk)`` tuple shape.
    """

    @pytest.mark.anyio
    async def test_duplicate_same_source_records_lowest_source_pk_wins(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Two active records of the same source: the lowest source_pk wins.

        Both rmi records share priority and source key, so the tiebreak is the
        source_pk; the first-created (lower id) record is the winner.
        """
        session = seeded_integration_session
        rid = await _create_resource_with_sources(
            session,
            test_user,
            {"source": "rmi", "name": "RMI First", "country": "USA"},
            {"source": "rmi", "name": "RMI Second", "country": "CAN"},
        )

        result = await resource_actions.get(session, rid)

        assert result.view.name == "RMI First"
        assert result.view.country == "USA"
        assert result.provenance["name"][0] == "RMI First"
        assert result.provenance["name"][1] == "rmi"

    @pytest.mark.anyio
    async def test_repointed_resource_with_active_membership_is_null_shell(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """A repointed resource coalesces to a null-shell, repointed_to populated.

        Even with an active membership carrying values, a repointed resource
        contributes no coalesced values; ``repointed_to`` carries its target.
        """
        session = seeded_integration_session
        root_id = await _create_resource_with_sources(
            session,
            test_user,
            {"source": "rmi", "name": "Root", "country": "USA"},
        )
        repointed_id = await _create_resource_with_sources(
            session,
            test_user,
            {"source": "gem", "name": "Repointed Name", "country": "CAN"},
            repointed_to=root_id,
        )

        result = await resource_actions.get(session, repointed_id)

        assert result.repointed_to == root_id
        assert result.view.name is None
        assert result.view.country is None
        assert result.provenance["name"] is None
        assert result.provenance["country"] is None

    @pytest.mark.anyio
    async def test_unlicensed_higher_priority_source_falls_through_in_detail(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """An unlicensed higher-priority source falls through to the next licensed.

        rmi outranks gem by default, but licensing only gem/wm/llm drops rmi, so
        the gem value wins in the detail view and provenance.
        """
        session = seeded_integration_session
        rid = await _create_resource_with_sources(
            session,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "country": "CAN"},
        )

        result = await resource_actions.get(
            session, rid, licensed_sources=frozenset({"gem", "wm", "llm"})
        )

        assert result.view.name == "GEM Name"
        assert result.provenance["name"][1] == "gem"

    @pytest.mark.anyio
    async def test_json_owners_operators_coalesced_in_detail(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """JSON owners/operators materialize in the detail view with provenance."""
        session = seeded_integration_session
        rid = await _create_resource_with_sources(
            session,
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

        result = await resource_actions.get(session, rid)

        assert result.view.owners is not None
        assert [(o.name, o.stake) for o in result.view.owners] == [("RMI Owner", 55.0)]
        assert result.provenance["owners"][1] == "rmi"
        assert result.view.operators is not None
        assert [(o.name, o.stake) for o in result.view.operators] == [
            ("RMI Operator", 100.0)
        ]
        assert result.provenance["operators"][1] == "rmi"

    @pytest.mark.anyio
    async def test_detail_reconstructs_source_data_from_single_query(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Detail builds the winner view *and* raw source_data from one query.

        Both projections come from the same ranked-candidate rows: the winner
        view/provenance (rn == 1) and source_data (all rows, grouped by source,
        best-priority first). Each source keeps its own per-field values.
        """
        session = seeded_integration_session
        rid = await _create_resource_with_sources(
            session,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "basin": "GEM Basin"},
        )

        result = await resource_actions.get(session, rid)

        # Winner view: rmi outranks gem for shared fields; gem fills basin.
        assert result.view.name == "RMI Name"
        assert result.view.country == "USA"
        assert result.view.basin == "GEM Basin"
        assert result.provenance["basin"][1] == "gem"

        # source_data: both sources, best-priority first, each with its own values.
        assert [s.source for s in result.source_data] == ["rmi", "gem"]
        by_source = {s.source: s for s in result.source_data}
        assert by_source["rmi"].name == "RMI Name"
        assert by_source["rmi"].basin is None
        assert by_source["gem"].basin == "GEM Basin"
        assert by_source["gem"].country is None

    @pytest.mark.anyio
    async def test_detail_hydration_round_trips_constant_in_source_count(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """get() costs a fixed number of round-trips regardless of source count.

        The view + source_data come from a single ranked query (no separate
        source-listing query, no per-source N+1), so a 4-source resource costs
        the same as a 1-source one.
        """
        one = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Only GEM", "country": "USA"},
        )
        many = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            *[
                {"source": src, "name": f"{src} Name", "country": "USA"}
                for src in ("rmi", "gem", "wm", "llm")
            ],
        )
        sync_engine = seeded_integration_session.bind.sync_engine

        async def _count(rid):
            executions = 0

            def _inc(conn, cursor, statement, parameters, context, executemany):
                nonlocal executions
                executions += 1

            event.listen(sync_engine, "before_cursor_execute", _inc)
            try:
                await resource_actions.get(seeded_integration_session, rid)
            finally:
                event.remove(sync_engine, "before_cursor_execute", _inc)
            return executions

        assert await _count(one) == await _count(many)


class TestBatchedSourceData:
    """ResourceModel.source_data_by_resource_id groups + licensed-filters."""

    @pytest.mark.anyio
    async def test_groups_by_resource_and_filters_licensed(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        session = seeded_integration_session
        rid_a = await _create_resource_with_sources(
            session,
            test_user,
            {"source": "rmi", "name": "A-RMI"},
            {"source": "gem", "name": "A-GEM"},
        )
        rid_b = await _create_resource_with_sources(
            session, test_user, {"source": "wm", "name": "B-WM"}
        )
        empty = ResourceModel.create(created_by=test_user)
        session.add(empty)
        await session.flush()

        by_id = await ResourceModel.source_data_by_resource_id(
            session, [rid_a, rid_b, empty.id]
        )
        assert {s.source for s, _ in by_id[rid_a]} == {"rmi", "gem"}
        assert {s.source for s, _ in by_id[rid_b]} == {"wm"}
        assert all(isinstance(prio, int) for _, prio in by_id[rid_a])
        assert by_id[empty.id] == []

        licensed = await ResourceModel.source_data_by_resource_id(
            session, [rid_a], licensed_sources=frozenset({"gem"})
        )
        assert {s.source for s, _ in licensed[rid_a]} == {"gem"}


class TestCoalescingEngineParity:
    """Phase-1 (SQL) and phase-2/detail (Python) coalescing pick the same winner.

    Exercises all three tiebreak paths at once: an unlicensed higher-priority
    source (dropped), a per-resource priority override, and duplicate
    same-source records (lowest source_pk wins).
    """

    @pytest.mark.anyio
    async def test_list_and_detail_agree_on_coalesced_winner(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        session = seeded_integration_session
        rid = await _create_resource_with_sources(
            session,
            test_user,
            # rmi has the top DEFAULT priority and would win the (priority=1,
            # source-ASC) tie against the wm override -- but it is left unlicensed
            # below, so it must fall through (the unlicensed-fallthrough path).
            {"source": "rmi", "name": "RMI Name", "country": "MEX"},
            {"source": "wm", "name": "WM First", "country": "USA"},
            {"source": "wm", "name": "WM Second", "country": "CAN"},
            {"source": "gem", "name": "GEM Name", "country": "BRA"},
        )
        # Override: wm becomes top priority for the NAME field, both wm records
        # curated in source_pk order (WM First < WM Second), so WM First wins.
        for priority, pk in enumerate(await _source_pks(session, rid, "wm")):
            session.add(
                OGFieldResourceSourcePriority.create(
                    created_by=test_user,
                    resource_id=rid,
                    source="wm",
                    source_pk=pk,
                    colname="name",
                    priority=priority,
                )
            )
        await session.flush()

        # rmi unlicensed -> falls through; among licensed sources wm (override)
        # wins, and the lowest source_pk among the duplicate wm records wins.
        licensed = frozenset({"wm", "gem"})

        # Detail (Python) winner.
        detail = await resource_actions.get(session, rid, licensed_sources=licensed)
        assert detail.view.name == "WM First"
        assert detail.provenance["name"][1] == "wm"

        # List/phase-1 (SQL): filtering on the detail winner's coalesced name must
        # return the resource, and the hydrated (phase-2) value + provenance match.
        params = _QueryParams(name=detail.view.name, page=1, page_size=10)
        items, total = await resource_actions.query(
            session, params, licensed_sources=licensed
        )
        assert total == 1
        assert [i.id for i in items] == [rid]
        assert items[0].data.name == detail.view.name
        assert items[0].provenance["name"] == detail.provenance["name"][1]


class TestCoalesceResources:
    """The shared SQL coalescing core used by detail + list.

    Produces the coalesced view + provenance; raw ``source_data`` is left empty
    here and attached by the detail path (``resource_model_to_entity``).
    """

    @pytest.mark.anyio
    async def test_entry_per_id_with_nullshell_for_empty(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        session = seeded_integration_session
        rid = await _create_resource_with_sources(
            session, test_user, {"source": "gem", "name": "G", "country": "USA"}
        )
        empty = ResourceModel.create(created_by=test_user)
        session.add(empty)
        await session.flush()

        out = await utils.coalesce_resources(session, [rid, empty.id])

        res = out[rid]
        assert res.view.name == "G"
        assert res.provenance["name"][1] == "gem"
        # coalesce_resources returns the coalesced view + provenance only; raw
        # sources are attached separately by the detail path.
        assert res.source_data == []

        empty_res = out[empty.id]
        assert empty_res.view.name is None
        assert empty_res.provenance["name"] is None
        assert empty_res.source_data == []

    @pytest.mark.anyio
    async def test_repointed_resource_yields_nullshell(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        session = seeded_integration_session
        target = await _create_resource_with_sources(
            session, test_user, {"source": "wm", "name": "Target"}
        )
        rid = await _create_resource_with_sources(
            session,
            test_user,
            {"source": "gem", "name": "G", "country": "USA"},
            repointed_to=target,
        )
        # The source query filters repointed_id IS NULL, so a repointed resource
        # returns no rows and coalesces to a null-shell.
        out = await utils.coalesce_resources(session, [rid])
        res = out[rid]
        assert res.view.name is None
        assert res.provenance["name"] is None
