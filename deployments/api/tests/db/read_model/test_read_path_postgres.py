"""Read-model list / filter-options output on a real Postgres (opt-in).

JSONB stores object keys in its own order, unlike SQLite's JSON, so only
Postgres shows whether serialized responses stay identical to live coalescing
(e.g. the provenance map's key order).
"""

from __future__ import annotations

import json
from typing import get_args

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db.read_model.permissions import PROFILES
from stitch.api.db.read_model.state import rebuild_all_resource_state
from stitch.api.entities import OGFieldQueryParams, SortableField, User

from .dataset import seed_dataset
from .postgres import requires_postgres

pytestmark = [pytest.mark.anyio, requires_postgres]

_SCENARIOS = [
    OGFieldQueryParams(page_size=50),
    OGFieldQueryParams(q="a", page=2, page_size=2),
    OGFieldQueryParams(country=["USA", "NOR"], basin=["Viking", "Permian"]),
    *(
        OGFieldQueryParams(sort_by=sort_by, sort_order=sort_order)
        for sort_by in get_args(SortableField)
        for sort_order in ("asc", "desc")
    ),
]


@pytest.mark.parametrize("mask", PROFILES)
async def test_serialized_output_matches_live(
    pg_session_factory: async_sessionmaker[AsyncSession], test_user: User, mask: int
):
    async with pg_session_factory() as session:
        await seed_dataset(session, test_user)
    await rebuild_all_resource_state(pg_session_factory)

    licensed = PROFILES[mask]
    async with pg_session_factory() as session:
        for params in _SCENARIOS:
            cached, cached_total = await resource_actions._query_read_model(
                session, params, mask
            )
            live, live_total = await resource_actions._query_live(
                session, params, licensed
            )
            assert cached_total == live_total
            assert json.dumps(
                [item.model_dump(mode="json") for item in cached]
            ) == json.dumps([item.model_dump(mode="json") for item in live]), params

        assert json.dumps(
            await resource_actions.filter_options(session, licensed)
        ) == json.dumps(await resource_actions._filter_options_live(session, licensed))
