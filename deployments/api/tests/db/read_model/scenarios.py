"""Multi-step scenarios shared by the SQLite and Postgres read-model tests."""

from __future__ import annotations

import asyncio
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db import og_field_source_actions as source_actions
from stitch.api.db.model import ResourceModel
from stitch.api.db.queries import resource_universe
from stitch.api.db.read_model import state
from stitch.api.db.read_model.permissions import PROFILES
from stitch.api.db.read_model.state import (
    _integrity_problems,
    is_resource_state_ready,
    rebuild_all_resource_state,
    refresh_resource_states,
)
from stitch.api.entities import OGFieldQueryParams, User
from stitch.ogsi.model import GemSource, OGFieldResource, RMISource

from tests.utils import make_source_record

from .dataset import attach, dump_state, new_resource

type SessionFactory = async_sessionmaker[AsyncSession]


async def rebuild_with_reads_and_writes_midway(
    factory: SessionFactory, user: User, monkeypatch
) -> None:
    """Pause a full rebuild after its first batch, read and write, then finish it.

    Six resources are rebuilt two per batch. While the rebuild waits before its
    second batch:

    * a reader that passed the readiness check just before the rebuild started
      lists resources straight from the table, and must get the full, correct
      answer (not an empty or partial table);
    * writes land on resources in the finished batch and in pending batches:
      attaches, a merge across both, and a brand-new resource.

    The finished rebuild must be ready, complete, and match a fresh recompute.
    """
    async with factory.begin() as session:
        ids = []
        for i in range(6):
            rid = await new_resource(session, user)
            await attach(session, user, rid, "gem", name=f"Seed {i}", country="USA")
            ids.append(rid)
        await refresh_resource_states(session, ids)

    rebuild_paused = asyncio.Event()
    resume_rebuild = asyncio.Event()
    rebuild: asyncio.Task[int] | None = None
    batches_started = 0
    real_refresh = state.refresh_resource_states

    async def pause_before_second_batch(
        session: AsyncSession, resource_ids: Collection[int]
    ) -> None:
        nonlocal batches_started
        # Only the rebuild's own batches pause; writes running meanwhile also
        # refresh through this function and must go straight through.
        if asyncio.current_task() is rebuild:
            batches_started += 1
            if batches_started == 2:
                rebuild_paused.set()
                await resume_rebuild.wait()
        await real_refresh(session, resource_ids)

    monkeypatch.setattr(state, "refresh_resource_states", pause_before_second_batch)
    rebuild = asyncio.create_task(rebuild_all_resource_state(factory, batch_size=2))
    await asyncio.wait_for(rebuild_paused.wait(), timeout=30)

    # A reader that saw ready=true just before the rebuild began.
    params = OGFieldQueryParams(page_size=50)
    async with factory() as session:
        cached = await resource_actions._query_read_model(session, params, mask=3)
        live = await resource_actions._query_live(session, params, PROFILES[3])
    assert cached == live, "an in-flight reader saw a partially rebuilt table"

    done, pending = ids[:2], ids[2:]
    async with factory.begin() as session:
        await source_actions.create_and_attach_source(
            session,
            user,
            RMISource(
                name="Done RMI", country="CAN", source_record=make_source_record()
            ),
            done[0],
        )
    async with factory.begin() as session:
        await source_actions.create_and_attach_source(
            session,
            user,
            RMISource(
                name="Pending RMI", country="CAN", source_record=make_source_record()
            ),
            pending[0],
        )
    async with factory.begin() as session:
        await resource_actions.apply_resource_merge(
            session, user, [done[1], pending[-1]]
        )
    async with factory.begin() as session:
        await resource_actions.create(
            session,
            user,
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

    resume_rebuild.set()
    await asyncio.wait_for(rebuild, timeout=60)

    async with factory() as session:
        assert await is_resource_state_ready(session)
        assert await _integrity_problems(session) == []
        listable = set((await session.scalars(resource_universe())).all())
        assert {rid for rid, _ in await dump_state(session)} == listable
        maintained = await dump_state(session)
        all_ids = (await session.scalars(select(ResourceModel.id))).all()
        await real_refresh(session, all_ids)
        assert await dump_state(session) == maintained
        await session.rollback()
