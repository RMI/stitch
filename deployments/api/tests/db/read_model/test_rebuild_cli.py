"""The rebuild / repair command (``python -m stitch.api.db.read_model.rebuild``)."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from stitch.api.db.model import OGFieldResourceState
from stitch.api.db.read_model import rebuild as rebuild_cli
from stitch.api.db.read_model.rebuild import ResourceStateRebuildError

from .dataset import Dataset, dump_state

pytestmark = pytest.mark.anyio

type SessionFactory = async_sessionmaker[AsyncSession]


class TestArgs:
    def test_parses_ids_and_batch_size(self):
        args = rebuild_cli._parse_args(["--ids", "3", "1", "--batch-size", "50"])
        assert args.ids == [3, 1]
        assert args.batch_size == 50

    def test_defaults_to_a_full_rebuild(self):
        args = rebuild_cli._parse_args([])
        assert args.ids is None
        assert args.batch_size == rebuild_cli.DEFAULT_BATCH_SIZE

    def test_rejects_non_positive_batch_size(self):
        with pytest.raises(SystemExit):
            rebuild_cli._parse_args(["--batch-size", "0"])

    def test_expected_failures_exit_non_zero_with_one_clear_line(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ):
        async def refuse(*_args: Any) -> None:
            raise ResourceStateRebuildError("No resource with id(s) [999999].")

        monkeypatch.setattr(rebuild_cli, "_run", refuse)
        with pytest.raises(SystemExit) as exited:
            rebuild_cli.main([])

        assert exited.value.code == 1
        assert "No resource with id(s) [999999]." in caplog.text


class TestCommand:
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

    async def _corrupt(self, session: AsyncSession, resource_id: int) -> None:
        await session.execute(
            update(OGFieldResourceState)
            .where(OGFieldResourceState.resource_id == resource_id)
            .values(name="corrupted")
        )
        await session.commit()

    async def test_full_rebuild(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        caplog: pytest.LogCaptureFixture,
    ):
        caplog.set_level(logging.INFO)
        await rebuild_cli._run(ids=None, batch_size=2)

        stored = await dump_state(seeded_integration_session)
        assert {rid for rid, _ in stored} == dataset.listable
        assert f"Rebuilt resource state for {len(dataset.listable)}" in caplog.text

    async def test_ids_refresh_only_those_resources(
        self,
        seeded_integration_session: AsyncSession,
        dataset: Dataset,
        caplog: pytest.LogCaptureFixture,
    ):
        caplog.set_level(logging.INFO)
        await rebuild_cli._run(ids=[dataset.gamma], batch_size=1)

        stored = await dump_state(seeded_integration_session)
        assert {rid for rid, _ in stored} == {dataset.gamma}
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

    async def test_unknown_ids_fail_without_changing_anything(
        self, seeded_integration_session: AsyncSession, rebuilt: Dataset
    ):
        session = seeded_integration_session
        await self._corrupt(session, rebuilt.alpha)
        corrupted = await dump_state(session)

        with pytest.raises(ResourceStateRebuildError, match="999999"):
            await rebuild_cli._run(ids=[rebuilt.alpha, 999_999], batch_size=1)

        # The valid id was not repaired either: nothing changed.
        assert await dump_state(session) == corrupted
