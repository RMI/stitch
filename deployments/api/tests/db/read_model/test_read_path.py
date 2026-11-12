"""List and filter-options are served from the resource-state read model."""

from __future__ import annotations

import asyncio
from collections.abc import Collection

import pytest
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db.model import OGFieldResourceState
from stitch.api.db.read_model import state
from stitch.api.db.read_model.permissions import PROFILES
from stitch.api.db.read_model.state import rebuild_all_resource_state
from stitch.api.entities import OGFieldFilterParams, OGFieldQueryParams, User

from .dataset import Dataset, attach, new_resource

pytestmark = pytest.mark.anyio

type SessionFactory = async_sessionmaker[AsyncSession]


async def _names(session: AsyncSession, licensed: Collection[str] | None) -> dict:
    items, _ = await resource_actions.query(
        session, OGFieldQueryParams(page_size=50), licensed
    )
    return {item.id: item.data.name for item in items}


class TestServedFromStoredState:
    async def test_list_reads_stored_rows_and_detail_coalesces_itself(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        """Overwrite a stored value: the list reflects it (proving it reads the
        table); the detail endpoint does not (it coalesces on every request)."""
        session = seeded_integration_session
        await session.execute(
            update(OGFieldResourceState)
            .where(OGFieldResourceState.resource_id == rebuilt.gamma)
            .values(name="Stored")
        )
        await session.commit()

        items, _ = await resource_actions.query(
            session, OGFieldQueryParams(id=rebuilt.gamma), PROFILES[3]
        )
        assert [item.data.name for item in items] == ["Stored"]

        detail = await resource_actions.get(session, rebuilt.gamma, PROFILES[3])
        assert detail.view is not None and detail.view.name == "Gamma"

    async def test_each_caller_gets_their_profiles_rows(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        session = seeded_integration_session
        public = await _names(session, PROFILES[0])
        with_wm = await _names(session, PROFILES[2])

        assert set(public) == set(with_wm) == rebuilt.listable
        assert (public[rebuilt.beta], with_wm[rebuilt.beta]) == ("Beta GEM", "Beta WM")
        assert (public[rebuilt.delta], with_wm[rebuilt.delta]) == (None, "Delta")

    async def test_internal_unscoped_calls_see_every_source(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        """``None`` (only internal callers pass it) has always meant every
        source; it reads the all-sources profile."""
        session = seeded_integration_session
        assert await _names(session, None) == await _names(session, PROFILES[3])
        assert await resource_actions.filter_options(
            session, OGFieldFilterParams()
        ) == await resource_actions.filter_options(
            session, OGFieldFilterParams(), PROFILES[3]
        )


class TestValuesTodaysModelRejects:
    async def test_only_the_page_showing_the_value_fails(
        self,
        seeded_integration_session: AsyncSession,
        integration_session_factory: SessionFactory,
        test_user: User,
    ):
        """A stored value can predate today's validation (e.g. a country code
        that is no longer valid). Building rows doesn't validate it; a list page
        does, so only a page that shows it fails."""
        session = seeded_integration_session
        good = await new_resource(session, test_user)
        await attach(session, test_user, good, "gem", name="Good", country="USA")
        legacy = await new_resource(session, test_user)
        await attach(
            session, test_user, legacy, "gem", name="Old GEM", country="Gemland"
        )
        await session.commit()
        await rebuild_all_resource_state(integration_session_factory)

        items, _ = await resource_actions.query(
            session, OGFieldQueryParams(id=good), PROFILES[3]
        )
        assert [item.data.name for item in items] == ["Good"]
        with pytest.raises(ValidationError):
            await resource_actions.query(
                session, OGFieldQueryParams(id=legacy), PROFILES[3]
            )


class TestReadsDuringARebuild:
    async def test_a_read_midway_through_a_rebuild_sees_every_resource(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        integration_session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """The rebuild replaces each batch's rows in its own transaction and never
        empties the table, so the API can keep serving while it runs."""
        session = seeded_integration_session
        expected = await _names(session, PROFILES[3])
        paused, resume = asyncio.Event(), asyncio.Event()
        real_refresh = state.refresh_resource_states
        batches = 0

        async def pause_before_second_batch(
            batch_session: AsyncSession, resource_ids: Collection[int]
        ) -> list[int]:
            nonlocal batches
            batches += 1
            if batches == 2:
                paused.set()
                await resume.wait()
            return await real_refresh(batch_session, resource_ids)

        monkeypatch.setattr(state, "refresh_resource_states", pause_before_second_batch)
        rebuild = asyncio.create_task(
            rebuild_all_resource_state(integration_session_factory, batch_size=2)
        )
        await asyncio.wait_for(paused.wait(), timeout=30)

        assert await _names(session, PROFILES[3]) == expected

        resume.set()
        await asyncio.wait_for(rebuild, timeout=30)
        assert await _names(session, PROFILES[3]) == expected
