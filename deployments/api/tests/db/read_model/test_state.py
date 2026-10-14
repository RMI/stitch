"""Building, refreshing, and rebuilding the resource-state read model."""

from __future__ import annotations

import logging
from collections.abc import Collection
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    OGFieldResourceState,
    OGFieldResourceStateStatus,
)
from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db.model.oil_gas_field_source_value import ATTRIBUTE_NAMES
from stitch.api.db.queries import resource_universe
from stitch.api.db.read_model import rebuild as rebuild_cli
from stitch.api.db.read_model import state
from stitch.api.db.read_model.permissions import (
    PERMISSION_MASKS,
    PROFILES,
    visible_sources_for_mask,
)
from stitch.api.db.read_model.state import (
    ResourceStateRebuildError,
    current_code_version,
    rebuild_resource_state_if_stale,
    _integrity_problems,
    is_resource_state_ready,
    lock_resources_statement,
    rebuild_all_resource_state,
    refresh_resource_state,
    refresh_resource_states,
)
from stitch.api.db.utils import coalesce_resources, resource_to_list_item_view
from stitch.api.entities import OGFieldQueryParams, User
from stitch.api.settings import get_settings
from stitch.ogsi.model import OGFieldListItemView
from stitch.ogsi.model.og_field import OilGasFieldBase

from .dataset import (
    ALPHA_OWNERS,
    BETA_OPERATORS,
    Dataset,
    attach,
    dump_state,
    new_resource,
)
from .scenarios import rebuild_with_reads_and_writes_midway

pytestmark = pytest.mark.anyio

type SessionFactory = async_sessionmaker[AsyncSession]


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
        recomputed = await refresh_resource_states(
            session,
            [dataset.inactive, dataset.bare, dataset.zeta_a, 999_999, dataset.alpha],
        )
        await session.commit()
        assert recomputed == [dataset.alpha]
        assert {rid for rid, _ in await dump_state(session)} == {dataset.alpha}

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


def _deploy(monkeypatch: pytest.MonkeyPatch, git_sha: str | None) -> None:
    """Run the rest of the test as code built from ``git_sha`` (None: no SHA)."""
    if git_sha is None:
        monkeypatch.delenv("GIT_SHA", raising=False)
    else:
        monkeypatch.setenv("GIT_SHA", git_sha)
    get_settings.cache_clear()


async def _set_disabled(session: AsyncSession, disabled: bool) -> None:
    """What the runbook's switch-off / switch-on SQL does."""
    await session.execute(update(OGFieldResourceStateStatus).values(disabled=disabled))
    await session.commit()


class TestDisabled:
    """An operator's switch-off sticks: rebuilds keep the rows current but never
    turn the read model back on; only clearing ``disabled`` does."""

    async def test_disabled_read_model_is_not_ready(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        session = seeded_integration_session
        await _set_disabled(session, True)
        assert not await is_resource_state_ready(session)

        await _set_disabled(session, False)
        assert await is_resource_state_ready(session)

    async def test_rebuilds_do_not_re_enable_it(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        integration_session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ):
        session = seeded_integration_session
        await _set_disabled(session, True)

        await rebuild_all_resource_state(integration_session_factory)
        _deploy(monkeypatch, "a-later-commit")
        await rebuild_resource_state_if_stale(integration_session_factory)

        status = (
            await session.execute(select(OGFieldResourceStateStatus.__table__))
        ).one()
        assert (status.ready, status.code_version, status.disabled) == (
            True,
            "a-later-commit",
            True,
        )
        assert not await is_resource_state_ready(session)

    async def test_if_stale_does_not_rebuild_a_current_disabled_table(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        integration_session_factory: SessionFactory,
    ):
        """Disabled isn't stale: deploys of the same commit don't rebuild."""
        session = seeded_integration_session
        await _set_disabled(session, True)
        built_at = await session.scalar(select(OGFieldResourceStateStatus.rebuilt_at))

        assert (
            await rebuild_resource_state_if_stale(integration_session_factory) is None
        )
        assert (
            await session.scalar(select(OGFieldResourceStateStatus.rebuilt_at))
            == built_at
        )

    async def test_cli_says_the_rebuilt_read_model_is_still_disabled(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        monkeypatch: pytest.MonkeyPatch,
        integration_engine: AsyncEngine,
        integration_session_factory: SessionFactory,
        caplog: pytest.LogCaptureFixture,
    ):
        async def _no_dispose() -> None:
            return None

        monkeypatch.setattr(
            rebuild_cli, "get_session_factory", lambda: integration_session_factory
        )
        monkeypatch.setattr(rebuild_cli, "dispose_engine", _no_dispose)
        monkeypatch.setattr(rebuild_cli, "get_engine", lambda: integration_engine)
        caplog.set_level(logging.INFO)
        await _set_disabled(seeded_integration_session, True)

        await rebuild_cli._run(ids=None, batch_size=500)

        assert "disabled" in caplog.text

    async def test_ids_repair_allowed_on_a_disabled_table_from_other_code(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        integration_session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
        integration_engine: AsyncEngine,
    ):
        """A disabled table isn't served, so the version guard doesn't apply."""
        session = seeded_integration_session
        _deploy(monkeypatch, "commit-a")
        await rebuild_all_resource_state(integration_session_factory)
        await _set_disabled(session, True)

        async def _no_dispose() -> None:
            return None

        monkeypatch.setattr(
            rebuild_cli, "get_session_factory", lambda: integration_session_factory
        )
        monkeypatch.setattr(rebuild_cli, "dispose_engine", _no_dispose)
        monkeypatch.setattr(rebuild_cli, "get_engine", lambda: integration_engine)
        _deploy(monkeypatch, "commit-b")
        await rebuild_cli._run(ids=[dataset.alpha], batch_size=1)


class TestCodeVersion:
    """The read model is used only by the commit whose rebuild produced it."""

    def test_code_version_is_the_builds_git_sha(self, monkeypatch: pytest.MonkeyPatch):
        _deploy(monkeypatch, "abc123")
        assert current_code_version() == "abc123"

    def test_code_version_without_a_git_sha_is_unknown(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _deploy(monkeypatch, None)
        assert current_code_version() == "unknown"

    async def test_rebuild_records_the_commit_that_built_it(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        integration_session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _deploy(monkeypatch, "commit-a")
        await rebuild_all_resource_state(integration_session_factory)

        session = seeded_integration_session
        status = (
            await session.execute(select(OGFieldResourceStateStatus.__table__))
        ).one()
        assert status.code_version == "commit-a"
        assert await is_resource_state_ready(session)

    async def test_deploying_other_code_turns_the_read_model_off_until_it_rebuilds(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        integration_session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ):
        session = seeded_integration_session
        _deploy(monkeypatch, "commit-a")
        await rebuild_all_resource_state(integration_session_factory)

        _deploy(monkeypatch, "commit-b")
        assert not await is_resource_state_ready(session)

        await rebuild_all_resource_state(integration_session_factory)
        assert await is_resource_state_ready(session)

        # Code from the previous deploy, still running during cutover, doesn't
        # trust rows built by the new commit.
        _deploy(monkeypatch, "commit-a")
        assert not await is_resource_state_ready(session)

    async def test_ready_row_from_before_versioning_is_not_ready(
        self, seeded_integration_session: AsyncSession
    ):
        """The migration leaves the existing row without a code version."""
        session = seeded_integration_session
        session.add(
            OGFieldResourceStateStatus(
                key="resource_state", ready=True, code_version=None
            )
        )
        await session.commit()
        assert not await is_resource_state_ready(session)

    async def test_targeted_refresh_does_not_change_the_code_version(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        integration_session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ):
        session = seeded_integration_session
        _deploy(monkeypatch, "commit-a")
        await rebuild_all_resource_state(integration_session_factory)

        _deploy(monkeypatch, "commit-b")
        await refresh_resource_states(session, [dataset.alpha])
        await session.commit()
        assert not await is_resource_state_ready(session)


async def _row_versions(session: AsyncSession) -> dict[int, set[str | None]]:
    """Each resource's set of row code versions."""
    rows = await session.execute(
        select(OGFieldResourceState.resource_id, OGFieldResourceState.code_version)
    )
    versions: dict[int, set[str | None]] = {}
    for rid, version in rows:
        versions.setdefault(rid, set()).add(version)
    return versions


class TestRowCodeVersions:
    """Each row records the commit that computed it; a rebuild redoes any row
    computed by other code, so an older API still writing during a cutover
    can't leave its rows in a table marked ready for the new commit."""

    async def test_rows_carry_the_code_that_computed_them(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        integration_session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ):
        session = seeded_integration_session
        _deploy(monkeypatch, "commit-a")
        await rebuild_all_resource_state(integration_session_factory)
        assert set().union(*(await _row_versions(session)).values()) == {"commit-a"}

        _deploy(monkeypatch, "commit-b")
        await refresh_resource_states(session, [dataset.alpha])
        await session.commit()
        versions = await _row_versions(session)
        assert versions[dataset.alpha] == {"commit-b"}
        assert versions[dataset.beta] == {"commit-a"}

    async def test_rebuild_redoes_rows_other_code_rewrote_during_it(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        integration_session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """GPT's cutover scenario: the new commit's rebuild has done a resource,
        then the old revision (still serving) writes it with the old rules."""
        session = seeded_integration_session
        _deploy(monkeypatch, "commit-b")
        first = min(dataset.listable)
        real_refresh = state.refresh_resource_states
        batches = 0

        async def old_code_writes_after_the_first_batch(
            batch_session: AsyncSession, resource_ids: Collection[int]
        ) -> list[int]:
            nonlocal batches
            batches += 1
            if batches == 2:
                with monkeypatch.context() as old_code:
                    old_code.setattr(state, "current_code_version", lambda: "commit-a")
                    async with integration_session_factory.begin() as other:
                        await real_refresh(other, [first])
            return await real_refresh(batch_session, resource_ids)

        monkeypatch.setattr(
            state, "refresh_resource_states", old_code_writes_after_the_first_batch
        )
        await rebuild_all_resource_state(integration_session_factory, batch_size=1)

        assert await is_resource_state_ready(session)
        versions = await _row_versions(session)
        assert versions[first] == {"commit-b"}
        assert set().union(*versions.values()) == {"commit-b"}

    async def test_rebuild_gives_up_if_other_code_keeps_writing(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        integration_session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ):
        session = seeded_integration_session
        _deploy(monkeypatch, "commit-b")
        real_refresh = state.refresh_resource_states

        async def other_code_rewrites_a_row_every_time(
            batch_session: AsyncSession, resource_ids: Collection[int]
        ) -> list[int]:
            recomputed = await real_refresh(batch_session, resource_ids)
            await batch_session.execute(
                update(OGFieldResourceState)
                .where(OGFieldResourceState.resource_id == min(dataset.listable))
                .values(code_version="commit-a")
            )
            return recomputed

        monkeypatch.setattr(
            state, "refresh_resource_states", other_code_rewrites_a_row_every_time
        )
        with pytest.raises(ResourceStateRebuildError, match="other code"):
            await rebuild_all_resource_state(integration_session_factory)
        assert not await is_resource_state_ready(session)

    async def test_if_stale_picks_up_where_a_failed_run_stopped(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        integration_session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _deploy(monkeypatch, "commit-b")
        real_compute = state._compute_state_rows
        computed: list[int] = []
        fail_on_batch: int | None = 2

        async def recording_compute(session: AsyncSession, ids: list[int]):
            if fail_on_batch is not None and len(computed) // 2 + 1 == fail_on_batch:
                raise RuntimeError("boom")
            computed.extend(ids)
            return await real_compute(session, ids)

        monkeypatch.setattr(state, "_compute_state_rows", recording_compute)
        with pytest.raises(RuntimeError, match="boom"):
            await rebuild_resource_state_if_stale(
                integration_session_factory, batch_size=2
            )
        done_first_time = list(computed)
        assert len(done_first_time) == 2

        computed.clear()
        fail_on_batch = None
        rebuilt_count = await rebuild_resource_state_if_stale(
            integration_session_factory, batch_size=2
        )

        assert sorted(computed) == sorted(dataset.listable - set(done_first_time))
        assert rebuilt_count == len(dataset.listable) - 2
        assert await is_resource_state_ready(seeded_integration_session)

    async def test_full_rebuild_recomputes_rows_already_from_this_code(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        integration_session_factory: SessionFactory,
    ):
        """A plain full rebuild is what you run after a restore or manual SQL:
        rows stamped with this commit can still be wrong then."""
        session = seeded_integration_session
        await _corrupt(session, rebuilt.alpha)
        await rebuild_all_resource_state(integration_session_factory)
        assert (await dump_state(session))[(rebuilt.alpha, 0)]["name"] == "Alpha RMI"


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

        real_compute = state._compute_state_rows
        batches = 0

        async def fail_on_second_batch(*args: Any, **kwargs: Any):
            nonlocal batches
            batches += 1
            if batches == 2:
                raise RuntimeError("boom")
            return await real_compute(*args, **kwargs)

        monkeypatch.setattr(state, "_compute_state_rows", fail_on_second_batch)
        with pytest.raises(RuntimeError, match="boom"):
            await rebuild_all_resource_state(integration_session_factory, batch_size=1)

        assert not await is_resource_state_ready(session)
        # The table was never emptied: every resource still has rows (rebuilt
        # or from before), but none are served until a rebuild succeeds.
        assert {rid for rid, _ in await dump_state(session)} == rebuilt.listable

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


class TestValuesTodaysModelRejects:
    """Stored values can predate today's validation (e.g. a country code that
    is no longer valid). Building state must not validate them: one such value
    would otherwise stop every full rebuild from finishing and fail every write
    to its resource, while the live list only fails on a page that shows it."""

    @pytest.fixture
    async def good_and_legacy(
        self, seeded_integration_session: AsyncSession, test_user: User
    ) -> tuple[int, int]:
        """A valid resource, and one whose winning country is no longer valid."""
        session = seeded_integration_session
        good = await new_resource(session, test_user)
        await attach(session, test_user, good, "gem", name="Good", country="USA")
        legacy = await new_resource(session, test_user)
        await attach(
            session, test_user, legacy, "gem", name="Old GEM", country="Gemland"
        )
        await attach(session, test_user, legacy, "rmi", name="Old RMI")
        await session.commit()
        return good, legacy

    async def test_full_rebuild_completes(
        self,
        seeded_integration_session: AsyncSession,
        integration_session_factory: SessionFactory,
        good_and_legacy: tuple[int, int],
    ):
        _, legacy = good_and_legacy
        await rebuild_all_resource_state(integration_session_factory)

        session = seeded_integration_session
        assert await is_resource_state_ready(session)
        assert (await dump_state(session))[(legacy, 0)]["country"] == "Gemland"

    async def test_writes_to_the_resource_still_succeed(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        good_and_legacy: tuple[int, int],
    ):
        _, legacy = good_and_legacy
        session = seeded_integration_session
        current = await resource_actions.field_source_values(session, legacy, "name")
        await resource_actions.set_field_source_priority(
            session,
            test_user,
            legacy,
            "name",
            [view.source_id for view in reversed(current)],
        )
        await session.commit()

        stored = await dump_state(session)
        assert stored[(legacy, 0)]["name"] == "Old GEM"
        assert stored[(legacy, 0)]["country"] == "Gemland"

    async def test_list_fails_only_where_live_fails(
        self,
        seeded_integration_session: AsyncSession,
        integration_session_factory: SessionFactory,
        good_and_legacy: tuple[int, int],
    ):
        good, legacy = good_and_legacy
        await rebuild_all_resource_state(integration_session_factory)
        session = seeded_integration_session
        licensed = PROFILES[3]

        good_page = OGFieldQueryParams(id=good)
        assert await resource_actions.query(
            session, good_page, licensed
        ) == await resource_actions._query_live(session, good_page, licensed)

        legacy_page = OGFieldQueryParams(id=legacy)
        with pytest.raises(ValidationError):
            await resource_actions._query_live(session, legacy_page, licensed)
        with pytest.raises(ValidationError):
            await resource_actions.query(session, legacy_page, licensed)


class TestRebuildAlongsideTraffic:
    async def test_reads_and_writes_midway_through_a_rebuild(
        self,
        seeded_integration_session: AsyncSession,
        integration_session_factory: SessionFactory,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ):
        await rebuild_with_reads_and_writes_midway(
            integration_session_factory, test_user, monkeypatch
        )


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

    async def test_reports_rows_computed_by_other_code(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        session = seeded_integration_session
        await session.execute(
            update(OGFieldResourceState)
            .where(OGFieldResourceState.resource_id == rebuilt.alpha)
            .values(code_version="some-other-commit")
        )
        assert await _integrity_problems(session) == [
            "1 listable resource(s) have rows computed by other code"
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

    def test_if_stale_is_off_by_default(self):
        assert rebuild_cli._parse_args([]).if_stale is False
        assert rebuild_cli._parse_args(["--if-stale"]).if_stale is True

    def test_if_stale_cannot_be_combined_with_ids(self):
        with pytest.raises(SystemExit):
            rebuild_cli._parse_args(["--if-stale", "--ids", "1"])

    def test_rebuild_errors_exit_non_zero_with_one_clear_line(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ):
        async def refuse(*_args: Any) -> None:
            raise ResourceStateRebuildError("Another rebuild is already running.")

        monkeypatch.setattr(rebuild_cli, "_run", refuse)
        with pytest.raises(SystemExit) as exited:
            rebuild_cli.main([])

        assert exited.value.code == 1
        assert "Another rebuild is already running." in caplog.text


class TestRebuildCli:
    @pytest.fixture(autouse=True)
    def _use_test_database(
        self,
        monkeypatch: pytest.MonkeyPatch,
        integration_engine: AsyncEngine,
        integration_session_factory: SessionFactory,
    ):
        async def _no_dispose() -> None:
            return None

        monkeypatch.setattr(
            rebuild_cli, "get_session_factory", lambda: integration_session_factory
        )
        monkeypatch.setattr(rebuild_cli, "dispose_engine", _no_dispose)
        monkeypatch.setattr(rebuild_cli, "get_engine", lambda: integration_engine)

    async def test_full_rebuild(
        self, seeded_integration_session: AsyncSession, dataset: Dataset
    ):
        await rebuild_cli._run(ids=None, batch_size=2)

        session = seeded_integration_session
        assert await is_resource_state_ready(session)
        assert {rid for rid, _ in await dump_state(session)} == dataset.listable

    async def test_if_stale_does_nothing_when_built_by_this_code(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        caplog: pytest.LogCaptureFixture,
    ):
        caplog.set_level(logging.INFO)
        session = seeded_integration_session
        built_at = await session.scalar(select(OGFieldResourceStateStatus.rebuilt_at))

        await rebuild_cli._run(ids=None, batch_size=2, if_stale=True)

        assert "already built by this code" in caplog.text
        assert (
            await session.scalar(select(OGFieldResourceStateStatus.rebuilt_at))
            == built_at
        )
        assert await is_resource_state_ready(session)

    @pytest.mark.parametrize("previously", ["never built", "built by other code"])
    async def test_if_stale_rebuilds_when_not_current(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        integration_session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        previously: str,
    ):
        caplog.set_level(logging.INFO)
        if previously == "built by other code":
            _deploy(monkeypatch, "previous-commit")
            await rebuild_all_resource_state(integration_session_factory)
        _deploy(monkeypatch, "this-commit")

        await rebuild_cli._run(ids=None, batch_size=2, if_stale=True)

        session = seeded_integration_session
        assert await is_resource_state_ready(session)
        assert {rid for rid, _ in await dump_state(session)} == dataset.listable
        assert "this-commit" in caplog.text

    async def test_ids_refresh_only_those_resources(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        caplog: pytest.LogCaptureFixture,
    ):
        caplog.set_level(logging.INFO)
        await rebuild_cli._run(ids=[dataset.gamma], batch_size=1)

        session = seeded_integration_session
        assert {rid for rid, _ in await dump_state(session)} == {dataset.gamma}
        assert not await is_resource_state_ready(session)
        assert f"Recomputed resource state for ids [{dataset.gamma}]" in caplog.text

    async def test_ids_that_are_not_listed_are_reported_not_recomputed(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        caplog: pytest.LogCaptureFixture,
    ):
        caplog.set_level(logging.INFO)
        # A stale row for a merged-away resource gets removed.
        await seeded_integration_session.execute(
            insert(OGFieldResourceState).values(
                resource_id=rebuilt.zeta_a, permission_mask=0, provenance={}
            )
        )
        await seeded_integration_session.commit()

        await rebuild_cli._run(ids=[rebuilt.alpha, rebuilt.zeta_a], batch_size=1)

        stored = {rid for rid, _ in await dump_state(seeded_integration_session)}
        assert rebuilt.zeta_a not in stored
        assert f"Recomputed resource state for ids [{rebuilt.alpha}]" in caplog.text
        assert f"[{rebuilt.zeta_a}]" in caplog.text
        assert "not listed" in caplog.text

    async def test_ids_refused_when_the_served_table_is_from_other_code(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        integration_session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Repairing from commit B would put B-computed rows into a table that
        commit A is serving as built entirely by A."""
        session = seeded_integration_session
        _deploy(monkeypatch, "commit-a")
        await rebuild_all_resource_state(integration_session_factory)
        await _corrupt(session, dataset.alpha)
        before = await dump_state(session)

        _deploy(monkeypatch, "commit-b")
        with pytest.raises(ResourceStateRebuildError, match="commit-a"):
            await rebuild_cli._run(ids=[dataset.alpha], batch_size=1)

        assert await dump_state(session) == before
        status = (
            await session.execute(select(OGFieldResourceStateStatus.__table__))
        ).one()
        assert (status.ready, status.code_version) == (True, "commit-a")

    async def test_ids_allowed_from_any_code_while_not_ready(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        integration_session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """A table that isn't ready isn't being served, and the next rebuild
        replaces its rows, so a repair from any code is harmless."""
        session = seeded_integration_session
        _deploy(monkeypatch, "commit-a")
        await rebuild_all_resource_state(integration_session_factory)
        await session.execute(update(OGFieldResourceStateStatus).values(ready=False))
        await session.commit()

        _deploy(monkeypatch, "commit-b")
        await rebuild_cli._run(ids=[dataset.alpha], batch_size=1)

        assert {rid for rid, _ in await dump_state(session)} >= {dataset.alpha}

    async def test_unknown_ids_fail_without_changing_anything(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        session = seeded_integration_session
        before = await dump_state(session)
        await _corrupt(session, rebuilt.alpha)
        corrupted = await dump_state(session)
        assert corrupted != before

        with pytest.raises(ResourceStateRebuildError, match="999999"):
            await rebuild_cli._run(ids=[rebuilt.alpha, 999_999], batch_size=1)

        # The valid id was not repaired either: nothing changed.
        assert await dump_state(session) == corrupted
