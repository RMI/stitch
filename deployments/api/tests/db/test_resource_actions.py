"""Database integration tests for domain-agnostic resource_actions."""

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    OilGasFieldSourceModel,
    ResourceModel,
)
from stitch.api.entities import (
    OGFieldFilterOptionsParams,
    OGFieldQueryParams,
    User,
)
from tests.factories import ResourceCreateFactory
from tests.utils import make_source_record


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
                status=MembershipStatus.ACTIVE,
            )
        )

    await session.flush()
    return resource.id


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
    async def test_explicit_source_filter_narrows_participating_memberships(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        included_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "country": "USA"},
        )
        await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "Only RMI", "country": "USA"},
        )

        params = _QueryParams(source=["gem"], page=1, page_size=10)
        items, total = await resource_actions.query(seeded_integration_session, params)

        assert total == 1
        assert [item.id for item in items] == [included_id]
        assert items[0].data.name == "GEM Name"
        assert items[0].provenance["name"] == "gem"

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
    async def test_licensed_sources_empty_returns_null_shells_for_all(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """An empty allowlist still returns rows, but with null-shell data."""
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "country": "CAN"},
        )

        params = _QueryParams(page=1, page_size=10)
        items, total = await resource_actions.query(
            seeded_integration_session,
            params,
            licensed_sources=frozenset(),
        )

        assert total == 1
        assert [item.id for item in items] == [resource_id]
        assert items[0].data.name is None
        assert items[0].data.country is None
        assert items[0].provenance["name"] is None
        assert items[0].provenance["country"] is None

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
        params = OGFieldFilterOptionsParams(field="basin")
        coalesced = resource_actions._build_licensed_resource_list_cte(
            params,
            licensed_sources=frozenset({"gem", "wm", "rmi", "llm"}),
        )
        col = resource_actions._resource_list_column(coalesced, params.field)
        assert col is not None

        value_col = resource_actions.cast(col, resource_actions.String).label("value")
        stmt = (
            resource_actions.select(value_col)
            .where(
                col.is_not(None),
                resource_actions.cast(col, resource_actions.String) != "",
            )
            .distinct()
            .order_by(value_col)
        )

        sql = str(
            stmt.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )

        assert (
            "SELECT DISTINCT CAST(licensed_resource_list.basin AS VARCHAR) AS value"
            in sql
        )
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

        params = _QueryParams(source=["wm"], page=1, page_size=10)
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
