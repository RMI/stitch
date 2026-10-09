"""list / filter-options served from the read model: parity with live, and fallback."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, get_args

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stitch.api.db import og_field_resource_actions as resource_actions
from stitch.api.db.model import OGFieldResourceState, OGFieldResourceStateStatus
from stitch.api.db.read_model.permissions import PROFILES, PUBLIC_SOURCES
from stitch.api.db.read_model.state import (
    rebuild_all_resource_state,
    refresh_resource_states,
)
from stitch.api.entities import OGFieldQueryParams, SortableField, User

from .dataset import Dataset, seed_dataset

pytestmark = pytest.mark.anyio

_PROFILE_IDS = {0: "public", 1: "public+ccr", 2: "public+wm", 3: "all"}


def _fail(name: str):
    async def fail(*_args: Any, **_kwargs: Any):
        raise AssertionError(f"{name} should not have been called")

    return fail


async def _assert_query_served_from_read_model(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    params: OGFieldQueryParams,
    licensed: frozenset[str],
) -> None:
    """``query`` answers from the read model, identically to live coalescing."""
    live = await resource_actions._query_live(session, params, licensed)
    with monkeypatch.context() as m:
        m.setattr(resource_actions, "_query_live", _fail("_query_live"))
        cached = await resource_actions.query(session, params, licensed)
    assert cached == live


_P = OGFieldQueryParams

# Each scenario builds its params from the dataset (some filter on its ids).
_SCENARIOS: dict[str, Callable[[Dataset], OGFieldQueryParams]] = {
    "default": lambda _: _P(),
    "second_page": lambda _: _P(page=2, page_size=2),
    "past_last_page": lambda _: _P(page=10, page_size=5),
    "q_name_case_insensitive": lambda _: _P(q="alpha"),
    "q_region": lambda _: _P(q="Sea"),
    "q_no_match": lambda _: _P(q="zzz"),
    "filter_name": lambda _: _P(name="Gamma"),
    "filter_name_local": lambda _: _P(name_local="Nowhere"),
    "filter_basin_multi": lambda _: _P(basin=["Viking", "Alb Basin", "Permian"]),
    "filter_state_province": lambda _: _P(state_province=["Rogaland"]),
    "filter_region": lambda _: _P(region=["North Sea", "North America"]),
    "filter_country_multi": lambda _: _P(country=["USA", "SAU", "GBR"]),
    "filter_field_status": lambda _: _P(field_status=["Producing"]),
    "filter_location_type": lambda _: _P(location_type="Onshore"),
    "filter_production_conventionality": lambda _: _P(
        production_conventionality="Mixed"
    ),
    "filter_primary_hydrocarbon_group": lambda _: _P(
        primary_hydrocarbon_group=["Dry Gas"]
    ),
    "filter_id": lambda ds: _P(id=ds.gamma),
    "filter_id_merged_away": lambda ds: _P(id=ds.zeta_a),
    "combined": lambda _: _P(
        country=["NOR", "USA", "CAN"],
        q="a",
        sort_by="basin",
        sort_order="desc",
        page=1,
        page_size=2,
    ),
}

_SORT_FIELDS = [f for f in get_args(SortableField)]


class TestListParity:
    @pytest.mark.parametrize("mask", PROFILES, ids=_PROFILE_IDS.get)
    @pytest.mark.parametrize("scenario", list(_SCENARIOS))
    async def test_scenario_matches_live(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        monkeypatch: pytest.MonkeyPatch,
        mask: int,
        scenario: str,
    ):
        await _assert_query_served_from_read_model(
            seeded_integration_session,
            monkeypatch,
            _SCENARIOS[scenario](rebuilt),
            PROFILES[mask],
        )

    # Sorting is profile-independent SQL; 0 (most nulls) and 3 (most values) suffice.
    @pytest.mark.parametrize("mask", [0, 3], ids=_PROFILE_IDS.get)
    @pytest.mark.parametrize("sort_order", ["asc", "desc"])
    @pytest.mark.parametrize("sort_by", _SORT_FIELDS)
    async def test_sort_matches_live(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        monkeypatch: pytest.MonkeyPatch,
        mask: int,
        sort_order: str,
        sort_by: str,
    ):
        await _assert_query_served_from_read_model(
            seeded_integration_session,
            monkeypatch,
            OGFieldQueryParams(sort_by=sort_by, sort_order=sort_order),
            PROFILES[mask],
        )


class TestFilterOptionsParity:
    @pytest.mark.parametrize("mask", PROFILES, ids=_PROFILE_IDS.get)
    async def test_matches_live(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        monkeypatch: pytest.MonkeyPatch,
        mask: int,
    ):
        session = seeded_integration_session
        licensed = PROFILES[mask]
        live = await resource_actions._filter_options_live(session, licensed)
        monkeypatch.setattr(
            resource_actions, "_filter_options_live", _fail("_filter_options_live")
        )
        cached = await resource_actions.filter_options(session, licensed)

        assert cached == live
        assert list(cached) == list(live)  # same field order in the response


class TestFallback:
    """When the read model can't answer exactly, ``query`` and ``filter_options``
    use live coalescing."""

    @pytest.fixture
    def read_model_forbidden(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            resource_actions, "_query_read_model", _fail("_query_read_model")
        )
        monkeypatch.setattr(
            resource_actions,
            "resource_state_filter_option_query",
            _fail("resource_state_filter_option_query"),
        )

    async def _assert_live_answer(
        self, session: AsyncSession, licensed: frozenset[str] | None
    ) -> None:
        params = OGFieldQueryParams()
        assert await resource_actions.query(
            session, params, licensed
        ) == await resource_actions._query_live(session, params, licensed)
        assert await resource_actions.filter_options(
            session, licensed
        ) == await resource_actions._filter_options_live(session, licensed)

    async def test_never_rebuilt(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        read_model_forbidden: None,
    ):
        await self._assert_live_answer(seeded_integration_session, PROFILES[3])

    async def test_not_ready_with_some_write_populated_rows(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        read_model_forbidden: None,
    ):
        """Rows written by write-path refreshes before the first full rebuild
        must not be served -- they cover only some resources."""
        session = seeded_integration_session
        await refresh_resource_states(session, [dataset.alpha])
        await session.commit()

        items, total = await resource_actions.query(
            session, OGFieldQueryParams(), PROFILES[3]
        )
        assert total == len(dataset.listable)
        await self._assert_live_answer(session, PROFILES[3])

    async def test_readiness_cleared_after_a_rebuild(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        read_model_forbidden: None,
    ):
        session = seeded_integration_session
        await session.execute(update(OGFieldResourceStateStatus).values(ready=False))
        await session.commit()
        await self._assert_live_answer(session, PROFILES[3])

    @pytest.mark.parametrize(
        "licensed",
        [
            None,
            PUBLIC_SOURCES - {"gem"},
            PUBLIC_SOURCES - {"nor"} | {"wm", "ccr"},
            frozenset({"wm"}),
            frozenset(),
        ],
        ids=[
            "unscoped",
            "partial_public",
            "partial_public_plus_both",
            "wm_only",
            "none",
        ],
    )
    async def test_unsupported_profile_while_ready(
        self,
        seeded_integration_session: AsyncSession,
        rebuilt: Dataset,
        read_model_forbidden: None,
        licensed: frozenset[str] | None,
    ):
        await self._assert_live_answer(seeded_integration_session, licensed)


class TestServedFromStoredState:
    async def test_list_reads_stored_rows_and_detail_stays_live(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        """Overwrite a stored value: the list reflects it (proving it reads the
        table), the detail endpoint does not (it always coalesces live)."""
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


class TestHttpResponsesUnchanged:
    """The serialized responses are byte-for-byte the same once the read model
    serves them (e.g. provenance key order survives JSONB storage)."""

    async def test_list_and_filter_options(
        self,
        integration_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ):
        async with integration_session_factory() as session:
            await seed_dataset(session, test_user)
        requests = [
            "/oil-gas-fields/?page_size=50",
            "/oil-gas-fields/?sort_by=latitude&sort_order=desc&page_size=3",
            "/oil-gas-fields/?country=USA&country=NOR&q=a",
            "/oil-gas-fields/filter-options",
        ]

        live = [(await integration_client.get(url)) for url in requests]
        await rebuild_all_resource_state(integration_session_factory)
        monkeypatch.setattr(resource_actions, "_query_live", _fail("_query_live"))
        monkeypatch.setattr(
            resource_actions, "_filter_options_live", _fail("_filter_options_live")
        )
        cached = [(await integration_client.get(url)) for url in requests]

        for url, before, after in zip(requests, live, cached, strict=True):
            assert before.status_code == after.status_code == 200, url
            assert after.text == before.text, url
