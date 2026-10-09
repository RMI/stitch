"""Every write that can change a cached answer keeps the read model in sync.

Each test runs a real write action on a rebuilt dataset, commits, and checks the
maintained state equals a from-scratch recompute of every resource. The lock
tests check that recomputes take the resource lock before reading anything; the
lock itself only has an effect on Postgres (see ``test_concurrency_postgres``).
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from stitch.api.db import merge_candidate_actions
from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db import og_field_source_actions as source_actions
from stitch.api.db.model import (
    MembershipModel,
    OilGasFieldSourceValueModel,
    ResourceModel,
)
from stitch.api.db.read_model import state
from stitch.api.db.read_model.permissions import PERMISSION_MASKS
from stitch.api.db.read_model.state import refresh_resource_states
from stitch.api.entities import MergeCandidateCreateRequest, User
from stitch.ogsi.model import GemSource, OGFieldResource, RMISource, WoodMacSource

from tests.utils import make_source_record

from .dataset import Dataset, dump_state

pytestmark = pytest.mark.anyio


async def _assert_matches_recompute(session: AsyncSession) -> None:
    """The committed, write-maintained state equals recomputing every resource."""
    maintained = await dump_state(session)
    all_ids = (await session.scalars(select(ResourceModel.id))).all()
    await refresh_resource_states(session, all_ids)
    assert await dump_state(session) == maintained
    await session.rollback()


def _resource_ids(stored: dict[tuple[int, int], Any]) -> set[int]:
    return {rid for rid, _ in stored}


class TestWritesKeepStateInSync:
    async def test_create_resource_with_sources(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        test_user: User,
    ):
        session = seeded_integration_session
        created = await resource_actions.create(
            session,
            test_user,
            OGFieldResource(
                source_data=[
                    GemSource(
                        name="Created",
                        country="BRA",
                        source_record=make_source_record(),
                    )
                ],
                constituents=frozenset(),
            ),
        )
        await session.commit()

        stored = await dump_state(session)
        assert stored[(created.id, 0)]["name"] == "Created"
        await _assert_matches_recompute(session)

    async def test_create_resource_without_sources_is_not_listed(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        test_user: User,
    ):
        session = seeded_integration_session
        created = await resource_actions.create(
            session,
            test_user,
            OGFieldResource(source_data=[], constituents=frozenset()),
        )
        await session.commit()

        assert created.id not in _resource_ids(await dump_state(session))
        await _assert_matches_recompute(session)

    async def test_create_and_attach_source(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        test_user: User,
    ):
        session = seeded_integration_session
        await source_actions.create_and_attach_source(
            session,
            test_user,
            RMISource(
                name="Beta RMI", country="SAU", source_record=make_source_record()
            ),
            rebuilt.beta,
        )
        await session.commit()

        stored = await dump_state(session)
        # rmi outranks both gem and wm.
        for mask in PERMISSION_MASKS:
            assert stored[(rebuilt.beta, mask)]["name"] == "Beta RMI"
        await _assert_matches_recompute(session)

    async def test_attach_existing_source(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        test_user: User,
    ):
        session = seeded_integration_session
        alpha_gem = await session.scalar(
            select(MembershipModel.source_pk).where(
                MembershipModel.resource_id == rebuilt.alpha,
                MembershipModel.source == "gem",
            )
        )
        existing = (await source_actions.get_sources(session, [alpha_gem]))[0]
        await source_actions.attach_sources_to_resource(
            session, rebuilt.delta, [existing], test_user
        )
        await session.commit()

        stored = await dump_state(session)
        assert stored[(rebuilt.delta, 0)]["name"] == "Alpha GEM"
        assert stored[(rebuilt.delta, 2)]["name"] == "Delta"
        await _assert_matches_recompute(session)

    async def test_set_field_source_priority(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        test_user: User,
    ):
        session = seeded_integration_session
        current = await resource_actions.field_source_values(
            session, rebuilt.alpha, "name"
        )
        await resource_actions.set_field_source_priority(
            session,
            test_user,
            rebuilt.alpha,
            "name",
            [view.source_id for view in reversed(current)],
        )
        await session.commit()

        stored = await dump_state(session)
        for mask in PERMISSION_MASKS:
            assert stored[(rebuilt.alpha, mask)]["name"] == "Alpha GEM"
        await _assert_matches_recompute(session)

    async def test_merge(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        test_user: User,
    ):
        session = seeded_integration_session
        merged = await resource_actions.apply_resource_merge(
            session, test_user, [rebuilt.beta, rebuilt.alpha]
        )
        await session.commit()

        stored_ids = _resource_ids(await dump_state(session))
        assert merged.id in stored_ids
        assert rebuilt.alpha not in stored_ids
        assert rebuilt.beta not in stored_ids
        await _assert_matches_recompute(session)

    async def test_approve_merge_candidate(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        test_user: User,
    ):
        session = seeded_integration_session
        candidate = await merge_candidate_actions.create_merge_candidate(
            session,
            test_user,
            MergeCandidateCreateRequest(resource_ids=[rebuilt.gamma, rebuilt.delta]),
        )
        approved = await merge_candidate_actions.approve_merge_candidate(
            session, test_user, candidate.id
        )
        await session.commit()

        stored_ids = _resource_ids(await dump_state(session))
        assert approved.merged_resource_id in stored_ids
        assert not {rebuilt.gamma, rebuilt.delta} & stored_ids
        await _assert_matches_recompute(session)

    async def test_rolled_back_write_leaves_state_unchanged(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        test_user: User,
    ):
        session = seeded_integration_session
        before = await dump_state(session)
        await source_actions.create_and_attach_source(
            session,
            test_user,
            WoodMacSource(
                name="Never committed",
                country="USA",
                source_record=make_source_record(),
            ),
            rebuilt.alpha,
        )
        await session.rollback()

        assert await dump_state(session) == before


class TestInPlaceSourceValueEdit:
    """No write path edits a stored source value today. If one is added, it changes
    every resource the source is attached to, so it must refresh all of them --
    the per-resource hooks above don't cover it."""

    async def test_must_refresh_every_resource_linked_to_the_source(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        session = seeded_integration_session
        # Zeta's gem source is attached to both the merged-away original and the
        # merged resource.
        zeta_gem = await session.scalar(
            select(MembershipModel.source_pk).where(
                MembershipModel.resource_id == rebuilt.zeta_a
            )
        )
        await session.execute(
            update(OilGasFieldSourceValueModel)
            .where(
                OilGasFieldSourceValueModel.source_pk == zeta_gem,
                OilGasFieldSourceValueModel.colname == "country",
            )
            .values(value_text="PAK")
        )
        await session.commit()

        # Without a refresh the cache is stale.
        assert (await dump_state(session))[(rebuilt.merged, 0)]["country"] == "IND"

        linked = (
            await session.scalars(
                select(MembershipModel.resource_id).where(
                    MembershipModel.source_pk == zeta_gem
                )
            )
        ).all()
        assert set(linked) == {rebuilt.zeta_a, rebuilt.merged}
        await refresh_resource_states(session, linked)
        await session.commit()

        assert (await dump_state(session))[(rebuilt.merged, 0)]["country"] == "PAK"
        await _assert_matches_recompute(session)


class TestLockBeforeRecompute:
    """Option (a): runs everywhere, checks the lock is taken before any read.

    SQLite doesn't render ``FOR UPDATE``, so the lock call is recorded with a
    spy alongside every SQL statement the engine executes.
    """

    @pytest.fixture
    def events(
        self, integration_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
    ) -> list[Any]:
        recorded: list[Any] = []

        def on_execute(conn, cursor, statement, parameters, context, executemany):
            recorded.append(statement)

        event.listen(
            integration_engine.sync_engine, "before_cursor_execute", on_execute
        )

        def spy(module: Any) -> None:
            real = module.lock_resources

            async def recording_lock(
                session: AsyncSession, resource_ids: Collection[int]
            ) -> None:
                recorded.append(("LOCK", sorted(set(resource_ids))))
                await real(session, resource_ids)

            monkeypatch.setattr(module, "lock_resources", recording_lock)

        spy(state)
        spy(resource_actions)
        yield recorded
        event.remove(
            integration_engine.sync_engine, "before_cursor_execute", on_execute
        )

    async def test_refresh_locks_before_any_read(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset, events: list
    ):
        session = seeded_integration_session
        events.clear()
        await refresh_resource_states(session, [rebuilt.beta, rebuilt.alpha])

        assert events[0] == ("LOCK", sorted([rebuilt.alpha, rebuilt.beta]))
        assert "FROM og_field_resources" in events[1]

    async def test_merge_locks_originals_in_id_order_before_reading_them(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        test_user: User,
        events: list,
    ):
        session = seeded_integration_session
        events.clear()
        await resource_actions.apply_resource_merge(
            session, test_user, [rebuilt.gamma, rebuilt.alpha, rebuilt.beta]
        )

        assert events[0] == (
            "LOCK",
            sorted([rebuilt.alpha, rebuilt.beta, rebuilt.gamma]),
        )
        locks = [e for e in events if isinstance(e, tuple)]
        # Then one refresh covering the originals and the new resource.
        assert len(locks) == 2
        assert set(locks[0][1]) < set(locks[1][1])

    @pytest.mark.parametrize("action", ["attach", "reprioritize"])
    async def test_write_actions_refresh_under_the_lock(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        test_user: User,
        events: list,
        action: str,
    ):
        session = seeded_integration_session
        if action == "attach":
            events.clear()
            await source_actions.create_and_attach_source(
                session,
                test_user,
                RMISource(
                    name="New", country="SAU", source_record=make_source_record()
                ),
                rebuilt.beta,
            )
            resource_id = rebuilt.beta
        else:
            current = await resource_actions.field_source_values(
                session, rebuilt.alpha, "name"
            )
            events.clear()
            await resource_actions.set_field_source_priority(
                session,
                test_user,
                rebuilt.alpha,
                "name",
                [view.source_id for view in reversed(current)],
            )
            resource_id = rebuilt.alpha

        lock_at = events.index(("LOCK", [resource_id]))
        state_writes = [
            i
            for i, e in enumerate(events)
            if isinstance(e, str) and "og_field_resource_state" in e
        ]
        assert state_writes, "the action did not touch the read model"
        assert all(i > lock_at for i in state_writes)
