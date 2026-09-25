"""Tests for the precomputed ``og_field_resource_state`` table and its refresh.

The table caches the ranked coalescing candidates the list/filter-options read
paths consume. These tests pin the two things that matter: the stored rows are
consistent with the live coalescing query, and a per-resource refresh matches a
full rebuild (so the write paths, which refresh incrementally, stay correct).
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    OGFieldResourceStateModel,
    ResourceModel,
)
from stitch.api.db.queries import (
    add_ranking,
    coalesced_state_winner_rows,
    construct_base_query_statement,
)
from stitch.api.db.resource_state import (
    rebuild_all_resource_state,
    refresh_resource_state,
)
from stitch.api.entities import User
from tests.utils import make_source_model


async def _build_resource(session: AsyncSession, user: User, *rows: dict) -> int:
    """Insert a resource with source records + active memberships (no refresh)."""
    resource = ResourceModel.create(created_by=user)
    session.add(resource)
    await session.flush()
    for row in rows:
        attrs = {k: v for k, v in row.items() if k != "source"}
        source = make_source_model(source=row["source"], created_by_id=user.id, **attrs)
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


async def _state_rows(session: AsyncSession, rid: int) -> list[tuple]:
    stmt = (
        select(
            OGFieldResourceStateModel.colname,
            OGFieldResourceStateModel.rank,
            OGFieldResourceStateModel.source,
        )
        .where(OGFieldResourceStateModel.resource_id == rid)
        .order_by(OGFieldResourceStateModel.colname, OGFieldResourceStateModel.rank)
    )
    return [tuple(r) for r in (await session.execute(stmt)).all()]


async def _snapshot(session: AsyncSession) -> set[tuple]:
    stmt = select(
        OGFieldResourceStateModel.resource_id,
        OGFieldResourceStateModel.colname,
        OGFieldResourceStateModel.rank,
        OGFieldResourceStateModel.source,
        OGFieldResourceStateModel.source_pk,
    )
    return {tuple(r) for r in (await session.execute(stmt)).all()}


def _live_winners(licensed_sources=None):
    """coalesced winner (resource_id, colname, source) from the live ranking CTE."""
    base = construct_base_query_statement(licensed_sources)
    winners = add_ranking(base).cte("live_winners")
    return select(winners.c.resource_id, winners.c.colname, winners.c.source)


async def _winner_map(session, builder, licensed=None) -> dict:
    rows = (await session.execute(builder(licensed))).all()
    return {(r.resource_id, r.colname): r.source for r in rows}


@pytest.mark.anyio
class TestResourceStateRefresh:
    async def test_stores_full_candidate_list_in_rank_order(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        # rmi(1) < wm(3) < gem(7) by default priority.
        rid = await _build_resource(
            session,
            test_user,
            {"source": "gem", "name": "GEM"},
            {"source": "wm", "name": "WM"},
            {"source": "rmi", "name": "RMI"},
        )
        await refresh_resource_state(session, [rid])

        # All candidates stored (no truncation), ranked best-first.
        assert await _state_rows(session, rid) == [
            ("name", 1, "rmi"),
            ("name", 2, "wm"),
            ("name", 3, "gem"),
        ]

    async def test_matches_live_coalescing_across_licensing(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        await _build_resource(
            session,
            test_user,
            {"source": "rmi", "name": "RMI", "country": "USA"},
            {"source": "wm", "name": "WM", "country": "CAN"},
            {"source": "gem", "name": "GEM", "country": "MEX"},
        )
        await rebuild_all_resource_state(session)

        for licensed in (None, frozenset({"gem"}), frozenset({"wm", "gem"})):
            state = await _winner_map(
                session,
                lambda lic: coalesced_state_winner_rows(lic),
                licensed,
            )
            live = await _winner_map(session, _live_winners, licensed)
            assert state == live, f"licensed={licensed}"

    async def test_refresh_of_repointed_resource_removes_rows(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        rid = await _build_resource(
            session, test_user, {"source": "gem", "name": "GEM"}
        )
        await refresh_resource_state(session, [rid])
        assert await _state_rows(session, rid) != []

        resource = await session.get(ResourceModel, rid)
        assert resource is not None
        resource.repointed_id = rid  # any non-null marks it merged-away
        await session.flush()
        await refresh_resource_state(session, [rid])

        assert await _state_rows(session, rid) == []

    async def test_refresh_matches_full_rebuild(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        await _build_resource(
            session,
            test_user,
            {"source": "rmi", "name": "RMI"},
            {"source": "gem", "name": "GEM", "country": "USA"},
        )
        await _build_resource(session, test_user, {"source": "wm", "name": "WM"})
        # Incremental refresh of every resource...
        roots = (
            await session.scalars(
                select(ResourceModel.id).where(ResourceModel.repointed_id.is_(None))
            )
        ).all()
        await refresh_resource_state(session, roots)
        incremental = await _snapshot(session)

        # ...must equal a from-scratch rebuild.
        await rebuild_all_resource_state(session)
        assert await _snapshot(session) == incremental

    async def test_rebuild_is_idempotent(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        await _build_resource(
            session,
            test_user,
            {"source": "rmi", "name": "RMI"},
            {"source": "gem", "name": "GEM"},
        )
        await rebuild_all_resource_state(session)
        first = await _snapshot(session)
        await rebuild_all_resource_state(session)
        assert await _snapshot(session) == first


@pytest.mark.anyio
class TestWritePathKeepsStateConsistent:
    async def test_merge_action_leaves_state_equal_to_rebuild(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        first = await _build_resource(
            session, test_user, {"source": "gem", "name": "First"}
        )
        second = await _build_resource(
            session, test_user, {"source": "wm", "name": "Second"}
        )
        await refresh_resource_state(session, [first, second])

        await resource_actions.apply_resource_merge(session, test_user, [first, second])

        after_action = await _snapshot(session)
        await rebuild_all_resource_state(session)
        assert await _snapshot(session) == after_action

    async def test_count_reflects_only_active_root_resources(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        rid = await _build_resource(
            session, test_user, {"source": "gem", "name": "GEM"}
        )
        await rebuild_all_resource_state(session)
        assert (
            await session.scalar(
                select(func.count()).select_from(OGFieldResourceStateModel)
            )
        ) == 1
        # The one row belongs to the resource we built.
        assert {r[0] for r in await _state_rows(session, rid)} == {"name"}
