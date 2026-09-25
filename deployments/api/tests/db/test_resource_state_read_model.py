"""Tests for the precomputed current-state read model (STIT-766).

Three concerns:

* **Parity** -- for every canonical visibility profile, the read-model-backed
  ``query``/``filter_options`` return exactly what live coalescing returns.
* **Permission masking** -- a restricted source's value only appears at masks that
  can see it.
* **Sync** -- after each mutating action the incrementally-maintained table equals
  a full rebuild from scratch.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    OGFieldResourceState,
    ResourceModel,
)
from stitch.api.db.model.oil_gas_field_source_value import ATTRIBUTE_NAMES
from stitch.api.db.og_field_resource_actions import (
    _filter_options_live,
    _query_live,
)
from stitch.api.db.read_model.permissions import (
    ALL_SOURCES,
    PUBLIC_SOURCES,
)
from stitch.api.db.priorities import seed_or_refresh_defaults
from stitch.api.db.read_model.state import rebuild_all_resource_state
from stitch.api.entities import OGFieldQueryParams, User
from tests.utils import make_source_model

pytestmark = pytest.mark.anyio

# The four canonical visibility profiles, one per permission_mask.
_PUBLIC = frozenset(PUBLIC_SOURCES)
_PROFILES = {
    "public": _PUBLIC,
    "public+ccr": _PUBLIC | {"ccr"},
    "public+wm": _PUBLIC | {"wm"},
    "all": frozenset(ALL_SOURCES),
}


async def _new_resource(session: AsyncSession, user: User) -> int:
    resource = ResourceModel.create(created_by=user)
    session.add(resource)
    await session.flush()
    return resource.id


async def _add(
    session: AsyncSession, user: User, rid: int, source: str, **attrs
) -> int:
    model = make_source_model(source=source, created_by_id=user.id, **attrs)
    session.add(model)
    await session.flush()
    session.add(
        MembershipModel.create(
            created_by=user,
            resource_id=rid,
            source=model.source,
            source_pk=model.id,
            status=MembershipStatus.ACTIVE,
        )
    )
    await session.flush()
    await seed_or_refresh_defaults(session, user, rid)
    return model.id


async def _seed_dataset(session: AsyncSession, user: User) -> list[int]:
    """A small dataset spanning public, wm and ccr sources with varied fields."""
    ids: list[int] = []

    # Public-only resource.
    r1 = await _new_resource(session, user)
    await _add(session, user, r1, "gem", name="Alpha", country="USA", basin="Permian")
    ids.append(r1)

    # wm outranks public for name; public still supplies basin.
    r2 = await _new_resource(session, user)
    await _add(session, user, r2, "gem", name="Beta GEM", country="SAU", basin="Ghawar")
    await _add(session, user, r2, "wm", name="Beta WM", country="SAU")
    ids.append(r2)

    # ccr supplies a value no public source has (region).
    r3 = await _new_resource(session, user)
    await _add(session, user, r3, "rmi", name="Gamma", country="NOR")
    await _add(session, user, r3, "ccr", region="North Sea", basin="Viking")
    ids.append(r3)

    # Resource whose only source is wm -> a null-shell for public viewers.
    r4 = await _new_resource(session, user)
    await _add(session, user, r4, "wm", name="Delta WM", country="GBR")
    ids.append(r4)

    await session.flush()
    return ids


def _row_key(row: OGFieldResourceState) -> tuple[int, int]:
    return (row.resource_id, row.permission_mask)


def _row_values(row: OGFieldResourceState) -> dict:
    values = {name: getattr(row, name) for name in ATTRIBUTE_NAMES}
    values["provenance"] = row.provenance
    return values


async def _dump_state(session: AsyncSession) -> dict[tuple[int, int], dict]:
    rows = (await session.scalars(select(OGFieldResourceState))).all()
    return {_row_key(row): _row_values(row) for row in rows}


_PARAM_SCENARIOS = {
    "default": OGFieldQueryParams(),
    "q_search": OGFieldQueryParams(q="Beta"),
    "filter_basin": OGFieldQueryParams(basin=["Ghawar", "Permian"]),
    "filter_country": OGFieldQueryParams(country=["SAU"]),
    "sort_country_desc": OGFieldQueryParams(sort_by="country", sort_order="desc"),
    "paged": OGFieldQueryParams(page=1, page_size=2, sort_by="name"),
}


class TestReadModelParity:
    @pytest.mark.parametrize("profile", list(_PROFILES))
    @pytest.mark.parametrize("scenario", list(_PARAM_SCENARIOS))
    async def test_query_matches_live(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        profile: str,
        scenario: str,
    ):
        session = seeded_integration_session
        await _seed_dataset(session, test_user)
        await rebuild_all_resource_state(session)

        licensed = _PROFILES[profile]
        params = _PARAM_SCENARIOS[scenario]

        model_items, model_total = await resource_actions.query(
            session, params, licensed_sources=licensed
        )
        live_items, live_total = await _query_live(
            session, params, licensed_sources=licensed
        )

        assert model_total == live_total
        assert [i.id for i in model_items] == [i.id for i in live_items]
        assert model_items == live_items

    @pytest.mark.parametrize("profile", list(_PROFILES))
    async def test_filter_options_match_live(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        profile: str,
    ):
        session = seeded_integration_session
        await _seed_dataset(session, test_user)
        await rebuild_all_resource_state(session)

        licensed = _PROFILES[profile]
        assert await resource_actions.filter_options(
            session, licensed_sources=licensed
        ) == await _filter_options_live(session, licensed_sources=licensed)


class TestPermissionMasking:
    async def test_restricted_value_hidden_below_its_mask(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        rid = await _new_resource(session, test_user)
        # Public source has no basin; only wm supplies it.
        await _add(session, test_user, rid, "gem", name="Shell", country="USA")
        await _add(session, test_user, rid, "wm", basin="WM Basin")
        await rebuild_all_resource_state(session)

        rows = {
            row.permission_mask: row
            for row in (
                await session.scalars(
                    select(OGFieldResourceState).where(
                        OGFieldResourceState.resource_id == rid
                    )
                )
            ).all()
        }
        # Four variants always stored.
        assert set(rows) == {0, 1, 2, 3}
        # basin only visible where wm is (masks 2 and 3).
        assert rows[0].basin is None
        assert rows[1].basin is None
        assert rows[2].basin == "WM Basin"
        assert rows[3].basin == "WM Basin"
        assert rows[2].provenance["basin"] == "wm"
        assert rows[0].provenance["basin"] is None


class TestReadModelSync:
    """After each mutating action, the maintained table equals a full rebuild."""

    async def _assert_synced(self, session: AsyncSession) -> None:
        before = await _dump_state(session)
        await rebuild_all_resource_state(session)
        after = await _dump_state(session)
        assert before == after

    async def test_synced_after_create(
        self,
        seeded_integration_session: AsyncSession,
        test_user: User,
        og_create_res_fact,
    ):
        session = seeded_integration_session
        await resource_actions.create(
            session, test_user, og_create_res_fact(name="Created")
        )
        await self._assert_synced(session)

    async def test_synced_after_attach(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        ids = await _seed_dataset(session, test_user)
        await rebuild_all_resource_state(session)
        # Attach a new source through the action path (refresh hook fires).
        from stitch.api.db.og_field_source_actions import attach_sources_to_resource
        from tests.utils import make_source
        from tests.factories import OGFieldBaseFactory

        base_fact = OGFieldBaseFactory
        await attach_sources_to_resource(
            session=session,
            resource_id=ids[0],
            source_rows=[make_source(base_fact, managed=False, source="bc")],
            user=test_user,
        )
        await self._assert_synced(session)

    async def test_synced_after_reprioritize(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        rid = await _new_resource(session, test_user)
        await _add(session, test_user, rid, "gem", name="GEM Name", country="USA")
        await _add(session, test_user, rid, "rmi", name="RMI Name", country="USA")
        await rebuild_all_resource_state(session)

        current = await resource_actions.field_source_values(session, rid, "name")
        reordered = [v.source_id for v in reversed(current)]
        await resource_actions.set_field_source_priority(
            session, test_user, rid, "name", reordered
        )
        await self._assert_synced(session)

    async def test_merge_removes_originals_and_syncs(
        self, seeded_integration_session: AsyncSession, test_user: User
    ):
        session = seeded_integration_session
        a = await _new_resource(session, test_user)
        await _add(session, test_user, a, "gem", name="A", country="USA")
        b = await _new_resource(session, test_user)
        await _add(session, test_user, b, "rmi", name="B", country="USA")
        await rebuild_all_resource_state(session)

        merged = await resource_actions.apply_resource_merge(session, test_user, [a, b])

        # Merged-away originals have no rows; the new target does.
        for original in (a, b):
            assert (
                await session.scalar(
                    select(OGFieldResourceState.resource_id).where(
                        OGFieldResourceState.resource_id == original
                    )
                )
                is None
            )
        assert (
            await session.scalar(
                select(OGFieldResourceState.resource_id).where(
                    OGFieldResourceState.resource_id == merged.id
                )
            )
            == merged.id
        )
        await self._assert_synced(session)
