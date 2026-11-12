"""Merge-candidate names and the name sort, on a real Postgres (opt-in).

The list names candidates in SQL from the read model, reading each winning
source out of the JSON ``provenance`` column. JSON access compiles differently
on Postgres (JSONB) and SQLite, so this checks the Postgres side (see
``postgres.py``); the always-on integration tests cover SQLite.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.api.db import merge_candidate_actions as mca
from stitch.api.db.model import MergeCandidateItemModel, MergeCandidateModel
from stitch.api.db.read_model.state import refresh_resource_states
from stitch.api.entities import MergeCandidateQueryParams, User

from .dataset import attach, new_resource
from .postgres import requires_postgres

pytestmark = [pytest.mark.anyio, requires_postgres]


async def _candidate(
    session: AsyncSession, user: User, sources: list[tuple[str, str]]
) -> list[int]:
    """A candidate over one new resource per ``(source, name)``, in order."""
    resource_ids = []
    for source, name in sources:
        rid = await new_resource(session, user)
        await attach(session, user, rid, source, name=name, country="USA")
        resource_ids.append(rid)
    candidate = MergeCandidateModel.create(
        created_by=user, fingerprint=mca._fingerprint(resource_ids)
    )
    session.add(candidate)
    await session.flush()
    session.add_all(
        MergeCandidateItemModel(
            merge_candidate_id=candidate.id, resource_id=rid, position=position
        )
        for position, rid in enumerate(resource_ids)
    )
    return resource_ids


async def test_names_follow_source_rank_and_sort_by_name(
    pg_session_factory: async_sessionmaker[AsyncSession], test_user: User
):
    async with pg_session_factory.begin() as session:
        bravo_ids = await _candidate(
            session, test_user, [("gem", "Zeta"), ("rmi", "Bravo")]
        )
        resource_ids = [
            # rmi outranks gem, though gem's resource comes first.
            *bravo_ids,
            # Same source: the earlier resource wins the tie.
            *await _candidate(
                session, test_user, [("gem", "Alpha"), ("gem", "Alpha twin")]
            ),
            # wm outranks gem.
            *await _candidate(
                session, test_user, [("gem", "Charlie"), ("wm", "Delta")]
            ),
        ]
        await refresh_resource_states(session, resource_ids)

    async with pg_session_factory() as session:
        names = {}
        for order in ("asc", "desc"):
            page = await mca.list_merge_candidates(
                session, MergeCandidateQueryParams(sort_by="name", sort_order=order)
            )
            names[order] = [item.name for item in page.items]
        bravo = next(item for item in page.items if item.name == "Bravo")
        detail = await mca.get_merge_candidate(session, bravo.id)

    assert names["asc"] == ["Alpha", "Bravo", "Delta"]
    # The detail view names its candidate with the same SQL.
    assert detail.name == "Bravo"
    assert detail.resource_ids == bravo_ids
    assert names["desc"] == ["Delta", "Bravo", "Alpha"]
