"""Building, refreshing, and rebuilding the resource-state read model."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    OGFieldResourceState,
    OGFieldResourceStateStatus,
)
from stitch.api.db.model.oil_gas_field_source_value import ATTRIBUTE_NAMES
from stitch.api.db.queries import resource_universe
from stitch.api.db.read_model import rebuild as rebuild_cli
from stitch.api.db.read_model import state
from stitch.api.db.read_model.permissions import (
    PERMISSION_MASKS,
    visible_sources_for_mask,
)
from stitch.api.db.read_model.state import (
    ResourceStateRebuildError,
    _integrity_problems,
    is_resource_state_ready,
    lock_resources_statement,
    rebuild_all_resource_state,
    refresh_resource_state,
    refresh_resource_states,
)
from stitch.api.db.utils import coalesce_resources, resource_to_list_item_view
from stitch.api.entities import User
from stitch.ogsi.model import OGFieldListItemView
from stitch.ogsi.model.og_field import OilGasFieldBase

from .dataset import ALPHA_OWNERS, BETA_OPERATORS, Dataset, dump_state, seed_dataset

pytestmark = pytest.mark.anyio

type SessionFactory = async_sessionmaker[AsyncSession]


@pytest.fixture
async def dataset(seeded_integration_session: AsyncSession, test_user: User) -> Dataset:
    return await seed_dataset(seeded_integration_session, test_user)


@pytest.fixture
async def rebuilt(
    dataset: Dataset, integration_session_factory: SessionFactory
) -> Dataset:
    await rebuild_all_resource_state(integration_session_factory)
    return dataset


def _cached_item(resource_id: int, stored: dict[str, Any]) -> OGFieldListItemView:
    return OGFieldListItemView(
        id=resource_id,
        data=OilGasFieldBase(**{field: stored[field] for field in ATTRIBUTE_NAMES}),
        provenance=stored["provenance"],
    )


async def _corrupt(session: AsyncSession, resource_id: int) -> None:
    await session.execute(
        update(OGFieldResourceState)
        .where(OGFieldResourceState.resource_id == resource_id)
        .values(name="corrupted")
    )
    await session.commit()


class TestBuilderParity:
    async def test_rows_exist_exactly_for_listable_resources(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        session = seeded_integration_session
        universe = set((await session.scalars(resource_universe())).all())
        stored = await dump_state(session)

        assert universe == rebuilt.listable
        assert set(stored) == {
            (rid, mask) for rid in rebuilt.listable for mask in PERMISSION_MASKS
        }

    @pytest.mark.parametrize("mask", PERMISSION_MASKS)
    async def test_stored_state_matches_live_coalescing(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset, mask: int
    ):
        session = seeded_integration_session
        stored = await dump_state(session)
        ids = sorted(rebuilt.listable)
        live = await coalesce_resources(session, ids, visible_sources_for_mask(mask))

        for rid in ids:
            row = stored[(rid, mask)]
            # Raw values, including their Python types (int vs float, JSON lists).
            for field in ATTRIBUTE_NAMES:
                winner = live[rid].provenance[field]
                expected = None if winner is None else winner[0]
                assert row[field] == expected, (rid, mask, field)
                assert type(row[field]) is type(expected), (rid, mask, field)
            # The list item the read path will build from the row.
            assert _cached_item(rid, row) == resource_to_list_item_view(live[rid])

    async def test_restricted_values_only_appear_in_profiles_that_see_them(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        stored = await dump_state(seeded_integration_session)

        beta = {mask: stored[(rebuilt.beta, mask)] for mask in PERMISSION_MASKS}
        assert [beta[m]["name"] for m in (0, 1, 2, 3)] == [
            "Beta GEM",
            "Beta GEM",
            "Beta WM",
            "Beta WM",
        ]
        assert [beta[m]["provenance"]["name"] for m in (0, 1, 2, 3)] == [
            "gem",
            "gem",
            "wm",
            "wm",
        ]
        assert beta[0]["operators"] is None
        assert beta[2]["operators"] == BETA_OPERATORS

        gamma = {mask: stored[(rebuilt.gamma, mask)] for mask in PERMISSION_MASKS}
        assert [gamma[m]["basin"] for m in (0, 1, 2, 3)] == [
            "Alb Basin",
            "Viking",
            "Alb Basin",
            "Viking",
        ]
        assert gamma[0]["region"] is None
        assert gamma[0]["provenance"]["region"] is None
        assert gamma[1]["region"] == "North Sea"

    async def test_wm_only_resource_is_a_null_shell_without_wm(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        stored = await dump_state(seeded_integration_session)
        for mask in (0, 1):
            row = stored[(rebuilt.delta, mask)]
            assert all(row[field] is None for field in ATTRIBUTE_NAMES)
            assert set(row["provenance"].values()) == {None}
        assert stored[(rebuilt.delta, 2)]["name"] == "Delta"

    async def test_per_resource_overrides_win(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        stored = await dump_state(seeded_integration_session)
        epsilon = {mask: stored[(rebuilt.epsilon, mask)] for mask in PERMISSION_MASKS}
        assert {epsilon[m]["name"] for m in PERMISSION_MASKS} == {"Epsilon NOR"}
        # By default wm outranks ccr; the override puts ccr first.
        assert [epsilon[m]["basin"] for m in (0, 1, 2, 3)] == [
            None,
            "CCR Basin",
            "WM Basin",
            "CCR Basin",
        ]

    async def test_json_and_numeric_values_round_trip(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        stored = await dump_state(seeded_integration_session)
        alpha = stored[(rebuilt.alpha, 0)]
        assert alpha["owners"] == ALPHA_OWNERS
        assert alpha["latitude"] == 31.5
        assert alpha["discovery_year"] == 1921
        assert isinstance(alpha["discovery_year"], int)
        assert alpha["provenance"]["owners"] == "gem"
        assert alpha["name"] == "Alpha RMI"

    async def test_merged_resource_combines_its_originals(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        stored = await dump_state(seeded_integration_session)
        merged = stored[(rebuilt.merged, 0)]
        assert merged["name"] == "Zeta RMI"
        assert merged["country"] == "IND"
        assert merged["longitude"] == 78.9


class TestTargetedRefresh:
    async def test_recomputes_only_requested_resources(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        session = seeded_integration_session
        pristine = await dump_state(session)
        await _corrupt(session, rebuilt.alpha)
        await _corrupt(session, rebuilt.beta)

        await refresh_resource_state(session, rebuilt.alpha)
        await session.commit()

        after = await dump_state(session)
        for mask in PERMISSION_MASKS:
            assert after[(rebuilt.alpha, mask)] == pristine[(rebuilt.alpha, mask)]
            assert after[(rebuilt.beta, mask)]["name"] == "corrupted"

    async def test_resource_that_stops_being_listable_loses_its_rows(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        session = seeded_integration_session
        await session.execute(
            update(MembershipModel)
            .where(MembershipModel.resource_id == rebuilt.delta)
            .values(status=MembershipStatus.INACTIVE)
        )
        await refresh_resource_state(session, rebuilt.delta)
        await session.commit()

        assert not any(rid == rebuilt.delta for rid, _ in await dump_state(session))

    async def test_unlisted_and_unknown_ids_get_no_rows(
        self, seeded_integration_session: AsyncSession, dataset: Dataset
    ):
        session = seeded_integration_session
        await refresh_resource_states(
            session, [dataset.inactive, dataset.bare, dataset.zeta_a, 999_999]
        )
        await session.commit()
        assert await dump_state(session) == {}

    async def test_does_not_mark_the_read_model_ready(
        self, seeded_integration_session: AsyncSession, dataset: Dataset
    ):
        """Write-path refreshes may populate rows before the first full rebuild;
        that partial state must stay invisible."""
        session = seeded_integration_session
        await refresh_resource_states(session, [dataset.alpha, dataset.beta])
        await session.commit()

        assert len(await dump_state(session)) == 2 * len(PERMISSION_MASKS)
        assert not await is_resource_state_ready(session)


class TestLocking:
    def test_locks_resource_rows_in_ascending_id_order(self):
        sql = str(
            lock_resources_statement([30, 10, 20, 10]).compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        assert "FROM og_field_resources" in sql
        assert "IN (10, 20, 30)" in sql
        assert sql.rstrip().endswith("ORDER BY og_field_resources.id FOR UPDATE"), sql


class TestFullRebuild:
    async def test_missing_status_row_is_not_ready(
        self, seeded_integration_session: AsyncSession
    ):
        assert not await is_resource_state_ready(seeded_integration_session)

    async def test_status_row_present_but_false_is_not_ready(
        self, seeded_integration_session: AsyncSession
    ):
        session = seeded_integration_session
        session.add(OGFieldResourceStateStatus(key="resource_state", ready=False))
        await session.commit()
        assert not await is_resource_state_ready(session)

    async def test_marks_ready_and_records_time(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        integration_session_factory: SessionFactory,
    ):
        count = await rebuild_all_resource_state(integration_session_factory)

        session = seeded_integration_session
        status = (
            await session.execute(select(OGFieldResourceStateStatus.__table__))
        ).one()
        assert count == len(dataset.listable)
        assert status.ready
        assert status.rebuilt_at is not None
        assert await is_resource_state_ready(session)

    async def test_is_idempotent(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        integration_session_factory: SessionFactory,
    ):
        first = await dump_state(seeded_integration_session)
        await rebuild_all_resource_state(integration_session_factory)
        assert await dump_state(seeded_integration_session) == first

    async def test_batch_size_does_not_change_the_result(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        integration_session_factory: SessionFactory,
    ):
        expected = await dump_state(seeded_integration_session)
        await rebuild_all_resource_state(integration_session_factory, batch_size=1)
        assert await dump_state(seeded_integration_session) == expected

    async def test_rejects_non_positive_batch_size(
        self, integration_session_factory: SessionFactory
    ):
        with pytest.raises(ValueError):
            await rebuild_all_resource_state(integration_session_factory, batch_size=0)

    async def test_repairs_corrupted_missing_and_stray_rows(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        integration_session_factory: SessionFactory,
    ):
        session = seeded_integration_session
        pristine = await dump_state(session)
        await _corrupt(session, rebuilt.alpha)
        await session.execute(
            delete(OGFieldResourceState).where(
                OGFieldResourceState.resource_id == rebuilt.beta,
                OGFieldResourceState.permission_mask == 2,
            )
        )
        await session.execute(
            insert(OGFieldResourceState).values(
                resource_id=rebuilt.zeta_a, permission_mask=0, provenance={}
            )
        )
        await session.commit()

        await rebuild_all_resource_state(integration_session_factory)
        assert await dump_state(session) == pristine

    async def test_failed_rebuild_leaves_read_model_not_ready(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        integration_session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ):
        session = seeded_integration_session
        assert await is_resource_state_ready(session)

        real_coalesce = state.coalesce_resources
        calls = 0

        async def fail_on_second_batch(*args: Any, **kwargs: Any):
            nonlocal calls
            calls += 1
            # One coalesce per profile per batch; fail inside the second batch.
            if calls > len(PERMISSION_MASKS):
                raise RuntimeError("boom")
            return await real_coalesce(*args, **kwargs)

        monkeypatch.setattr(state, "coalesce_resources", fail_on_second_batch)
        with pytest.raises(RuntimeError, match="boom"):
            await rebuild_all_resource_state(integration_session_factory, batch_size=1)

        assert not await is_resource_state_ready(session)
        # Only the first batch committed; the partial rows are not served.
        assert len({rid for rid, _ in await dump_state(session)}) == 1

    async def test_incomplete_result_fails_integrity_check(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        integration_session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ):
        real_compute = state._compute_state_rows

        async def drop_one_profile(session: AsyncSession, ids: list[int]):
            rows = await real_compute(session, ids)
            return [row for row in rows if row["permission_mask"] != 3]

        monkeypatch.setattr(state, "_compute_state_rows", drop_one_profile)
        with pytest.raises(ResourceStateRebuildError, match="lack a row"):
            await rebuild_all_resource_state(integration_session_factory)

        assert not await is_resource_state_ready(seeded_integration_session)


class TestIntegrityCheck:
    async def test_clean_state_has_no_problems(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        assert await _integrity_problems(seeded_integration_session) == []

    async def test_reports_missing_profile_rows(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        session = seeded_integration_session
        await session.execute(
            delete(OGFieldResourceState).where(
                OGFieldResourceState.resource_id == rebuilt.alpha,
                OGFieldResourceState.permission_mask == 1,
            )
        )
        assert await _integrity_problems(session) == [
            "1 listable resource(s) lack a row for every permission profile"
        ]

    async def test_reports_rows_for_merged_away_resources(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        session = seeded_integration_session
        await session.execute(
            insert(OGFieldResourceState).values(
                resource_id=rebuilt.zeta_b, permission_mask=0, provenance={}
            )
        )
        assert await _integrity_problems(session) == [
            "1 non-listable resource(s) have stored state"
        ]


class TestRebuildCliArgs:
    def test_parses_ids_and_batch_size(self):
        args = rebuild_cli._parse_args(["--ids", "3", "1", "--batch-size", "50"])
        assert args.ids == [3, 1]
        assert args.batch_size == 50

    def test_rejects_non_positive_batch_size(self):
        with pytest.raises(SystemExit):
            rebuild_cli._parse_args(["--batch-size", "0"])


class TestRebuildCli:
    @pytest.fixture(autouse=True)
    def _use_test_database(
        self,
        monkeypatch: pytest.MonkeyPatch,
        integration_session_factory: SessionFactory,
    ):
        async def _no_dispose() -> None:
            return None

        monkeypatch.setattr(
            rebuild_cli, "get_session_factory", lambda: integration_session_factory
        )
        monkeypatch.setattr(rebuild_cli, "dispose_engine", _no_dispose)

    async def test_full_rebuild(
        self, seeded_integration_session: AsyncSession, dataset: Dataset
    ):
        await rebuild_cli._run(ids=None, batch_size=2)

        session = seeded_integration_session
        assert await is_resource_state_ready(session)
        assert {rid for rid, _ in await dump_state(session)} == dataset.listable

    async def test_ids_refresh_only_those_resources(
        self, seeded_integration_session: AsyncSession, dataset: Dataset
    ):
        await rebuild_cli._run(ids=[dataset.gamma], batch_size=1)

        session = seeded_integration_session
        assert {rid for rid, _ in await dump_state(session)} == {dataset.gamma}
        assert not await is_resource_state_ready(session)
