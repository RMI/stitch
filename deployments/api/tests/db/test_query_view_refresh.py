"""Integration tests for the EAV projection write path (og_field_query_view_refresh)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db import og_field_query_view_refresh as refresh
from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    OGFieldResourceQueryView,
    OilGasFieldSourceModel,
    ResourceModel,
)
from stitch.api.entities import User
from tests.utils import make_source_record


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


async def _rows_for(
    session: AsyncSession, resource_id: int
) -> list[OGFieldResourceQueryView]:
    result = await session.scalars(
        select(OGFieldResourceQueryView).where(
            OGFieldResourceQueryView.resource_id == resource_id
        )
    )
    return list(result.all())


def _by_column(
    rows: list[OGFieldResourceQueryView],
) -> dict[tuple[int, str], OGFieldResourceQueryView]:
    """Index rows by (source_id, column_name)."""
    return {(r.source_id, r.column_name): r for r in rows}


class TestRefreshResources:
    @pytest.mark.anyio
    async def test_scalar_value_routing_and_denormalization(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Case 1: scalar routing + denormalized source/priority/column_name."""
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {
                "source": "gem",
                "name": "Ghawar",
                "country": "SAU",
                "discovery_year": 1948,
                "latitude": 25.4,
            },
        )

        await refresh.rebuild_all(seeded_integration_session)

        rows = await _rows_for(seeded_integration_session, resource_id)
        indexed = _by_column(rows)
        source_id = rows[0].source_id

        name_row = indexed[(source_id, "name")]
        assert name_row.value_text == "Ghawar"
        assert name_row.value_num is None
        assert name_row.value_json is None
        assert name_row.source == "gem"
        # gem priority == 3 from DEFAULT_PRIORITIES
        assert name_row.priority == 3
        assert name_row.column_name == "name"

        assert indexed[(source_id, "country")].value_text == "SAU"
        assert indexed[(source_id, "discovery_year")].value_num == 1948.0
        assert indexed[(source_id, "latitude")].value_num == 25.4

    @pytest.mark.anyio
    async def test_value_num_holds_float(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Case 2: int years coerced to float; lat/long stay float."""
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {
                "source": "rmi",
                "name": "F",
                "country": "USA",
                "discovery_year": 1948,
                "latitude": 12.5,
            },
        )

        await refresh.refresh_resources(seeded_integration_session, [resource_id])

        rows = await _rows_for(seeded_integration_session, resource_id)
        indexed = _by_column(rows)
        source_id = rows[0].source_id

        dy = indexed[(source_id, "discovery_year")].value_num
        assert dy == 1948.0
        assert isinstance(dy, float)
        lat = indexed[(source_id, "latitude")].value_num
        assert lat == 12.5
        assert isinstance(lat, float)

    @pytest.mark.anyio
    async def test_json_routing_owners_and_operators(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Case 3: owners/operators lists routed to value_json."""
        owners = [{"name": "Owner A", "stake": 60.0}]
        operators = [{"name": "Op A", "stake": 100.0}]
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {
                "source": "rmi",
                "name": "F",
                "country": "USA",
                "owners": owners,
                "operators": operators,
            },
        )

        await refresh.refresh_resources(seeded_integration_session, [resource_id])

        rows = await _rows_for(seeded_integration_session, resource_id)
        indexed = _by_column(rows)
        source_id = rows[0].source_id

        owners_row = indexed[(source_id, "owners")]
        assert owners_row.value_json == owners
        assert owners_row.value_text is None
        assert owners_row.value_num is None

        operators_row = indexed[(source_id, "operators")]
        assert operators_row.value_json == operators

    @pytest.mark.anyio
    async def test_empty_list_is_present(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Case 4: owners=[] emits a present row with value_json == [] (not skipped/NULL)."""
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {
                "source": "rmi",
                "name": "F",
                "country": "USA",
                "owners": [],
            },
        )

        await refresh.refresh_resources(seeded_integration_session, [resource_id])

        rows = await _rows_for(seeded_integration_session, resource_id)
        indexed = _by_column(rows)
        source_id = rows[0].source_id

        assert (source_id, "owners") in indexed
        owners_row = indexed[(source_id, "owners")]
        assert owners_row.value_json == []
        assert owners_row.value_json is not None

    @pytest.mark.anyio
    async def test_none_field_emits_no_row(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Case 5: None field -> no row emitted (owners=None and a scalar None)."""
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {
                "source": "rmi",
                "name": "F",
                "country": "USA",
                "owners": None,
                "basin": None,
            },
        )

        await refresh.refresh_resources(seeded_integration_session, [resource_id])

        rows = await _rows_for(seeded_integration_session, resource_id)
        indexed = _by_column(rows)
        source_id = rows[0].source_id

        assert (source_id, "owners") not in indexed
        assert (source_id, "basin") not in indexed
        # present scalars still emitted
        assert (source_id, "name") in indexed

    @pytest.mark.anyio
    async def test_empty_string_is_present(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Empty string "" is PRESENT and stored as value_text="" (companion to case 4/5)."""
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {
                "source": "rmi",
                "name": "F",
                "country": "USA",
                "basin": "",
            },
        )

        await refresh.refresh_resources(seeded_integration_session, [resource_id])

        rows = await _rows_for(seeded_integration_session, resource_id)
        indexed = _by_column(rows)
        source_id = rows[0].source_id

        assert (source_id, "basin") in indexed
        assert indexed[(source_id, "basin")].value_text == ""

    @pytest.mark.anyio
    async def test_repointed_resource_has_no_rows_after_rebuild(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Case 6: repointed resource -> no rows after rebuild_all."""
        root_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Root", "country": "USA"},
        )
        repointed_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Repointed", "country": "USA"},
            repointed_to=root_id,
        )

        await refresh.rebuild_all(seeded_integration_session)

        assert await _rows_for(seeded_integration_session, repointed_id) == []
        assert len(await _rows_for(seeded_integration_session, root_id)) > 0

    @pytest.mark.anyio
    async def test_inactive_membership_excluded(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Case 7: inactive membership contributes no rows."""
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Inactive", "country": "USA"},
            status=MembershipStatus.INACTIVE,
        )

        await refresh.rebuild_all(seeded_integration_session)

        assert await _rows_for(seeded_integration_session, resource_id) == []

    @pytest.mark.anyio
    async def test_refresh_resources_idempotency(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Case 8: running refresh twice yields identical row set."""
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {
                "source": "gem",
                "name": "Idem",
                "country": "USA",
                "owners": [{"name": "O", "stake": 50.0}],
            },
        )

        await refresh.refresh_resources(seeded_integration_session, [resource_id])
        first = await _rows_for(seeded_integration_session, resource_id)
        first_set = {
            (r.source_id, r.column_name, r.value_text, r.value_num, str(r.value_json))
            for r in first
        }

        await refresh.refresh_resources(seeded_integration_session, [resource_id])
        second = await _rows_for(seeded_integration_session, resource_id)
        second_set = {
            (r.source_id, r.column_name, r.value_text, r.value_num, str(r.value_json))
            for r in second
        }

        assert len(first) == len(second)
        assert first_set == second_set

    @pytest.mark.anyio
    async def test_refresh_of_now_repointed_resource_removes_rows(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Case 9: a resource with rows, then repointed, then refreshed -> zero rows."""
        root_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Root", "country": "USA"},
        )
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "WillRepoint", "country": "USA"},
        )

        await refresh.refresh_resources(seeded_integration_session, [resource_id])
        assert len(await _rows_for(seeded_integration_session, resource_id)) > 0

        resource = await seeded_integration_session.get(ResourceModel, resource_id)
        assert resource is not None
        resource.repointed_id = root_id
        await seeded_integration_session.flush()

        await refresh.refresh_resources(seeded_integration_session, [resource_id])
        assert await _rows_for(seeded_integration_session, resource_id) == []

    @pytest.mark.anyio
    async def test_multi_source_resource_carries_per_source_metadata(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Case 10: each source's rows carry that source's source_id/source/priority."""
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "rmi", "name": "RMI Name", "country": "USA"},
            {"source": "gem", "name": "GEM Name", "country": "CAN"},
        )

        await refresh.refresh_resources(seeded_integration_session, [resource_id])

        rows = await _rows_for(seeded_integration_session, resource_id)
        name_rows = [r for r in rows if r.column_name == "name"]
        assert len(name_rows) == 2

        by_source = {r.source: r for r in name_rows}
        assert by_source["rmi"].value_text == "RMI Name"
        assert by_source["rmi"].priority == 1  # rmi priority
        assert by_source["gem"].value_text == "GEM Name"
        assert by_source["gem"].priority == 3  # gem priority

        # each row carries the matching source_id from its membership
        for r in name_rows:
            membership = await seeded_integration_session.scalar(
                select(MembershipModel).where(
                    MembershipModel.resource_id == resource_id,
                    MembershipModel.source == r.source,
                )
            )
            assert membership is not None
            assert r.source_id == membership.source_pk

    @pytest.mark.anyio
    async def test_refresh_resources_empty_is_noop(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """Empty resource_ids returns early without touching the table."""
        resource_id = await _create_resource_with_sources(
            seeded_integration_session,
            test_user,
            {"source": "gem", "name": "Keep", "country": "USA"},
        )
        await refresh.refresh_resources(seeded_integration_session, [resource_id])
        before = len(await _rows_for(seeded_integration_session, resource_id))

        await refresh.refresh_resources(seeded_integration_session, [])

        after = len(await _rows_for(seeded_integration_session, resource_id))
        assert before == after
        assert before > 0

    @pytest.mark.anyio
    async def test_resource_with_no_active_memberships_has_no_rows(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
    ):
        """A resource with no active memberships ends with no rows."""
        resource = ResourceModel.create(created_by=test_user)
        seeded_integration_session.add(resource)
        await seeded_integration_session.flush()

        await refresh.refresh_resources(seeded_integration_session, [resource.id])

        assert await _rows_for(seeded_integration_session, resource.id) == []
