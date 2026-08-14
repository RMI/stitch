from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import BaseModel

from stitch.entity_linkage.jobs import (
    JobAlreadyRunningError,
    JobState,
    get_job_manager,
    reset_manager,
)


class _Params(BaseModel):
    n: int = 0


class _Result(BaseModel):
    doubled: int


@pytest.fixture(autouse=True)
def _reset():
    reset_manager()
    yield
    reset_manager()


def test_get_job_manager_returns_singleton() -> None:
    assert get_job_manager() is get_job_manager()


def test_reset_manager_drops_state() -> None:
    first = get_job_manager()
    reset_manager()
    assert get_job_manager() is not first


def test_run_thunk_success_records_result() -> None:
    async def scenario() -> None:
        mgr = get_job_manager()

        async def run() -> _Result:
            return _Result(doubled=6)

        record = await mgr.start(_Params(n=3), run)
        assert record.state == JobState.running
        for _ in range(200):
            if mgr.current().state != JobState.running:
                break
            await asyncio.sleep(0.01)
        assert mgr.current().state == JobState.succeeded
        assert mgr.current().result.model_dump() == {"doubled": 6}
        assert mgr.current().params.model_dump() == {"n": 3}
        assert mgr.current().finished_at is not None

    asyncio.run(scenario())


def test_run_thunk_failure_records_error() -> None:
    async def scenario() -> None:
        mgr = get_job_manager()

        async def run() -> _Result:
            raise RuntimeError("kaboom")

        await mgr.start(_Params(), run)
        for _ in range(200):
            if mgr.current().state != JobState.running:
                break
            await asyncio.sleep(0.01)
        assert mgr.current().state == JobState.failed
        assert mgr.current().error == "RuntimeError: kaboom"
        assert mgr.current().result is None

    asyncio.run(scenario())


def test_run_thunk_failure_records_type_when_message_is_empty() -> None:
    """The shape that produced a blank ``error`` in the PR-0224 incident.

    httpx timeout exceptions stringify to ``""``, so recording ``str(exc)``
    alone left the job record saying only "failed".
    """

    async def scenario() -> None:
        mgr = get_job_manager()

        async def run() -> _Result:
            raise httpx.ReadTimeout("")

        await mgr.start(_Params(), run)
        for _ in range(200):
            if mgr.current().state != JobState.running:
                break
            await asyncio.sleep(0.01)
        assert mgr.current().state == JobState.failed
        assert mgr.current().error == "ReadTimeout"

    asyncio.run(scenario())


def test_progress_object_is_visible_on_the_record_while_running() -> None:
    """The caller mutates its own object; the record reflects it live."""

    class _Progress(BaseModel):
        scanned: int = 0

    async def scenario() -> None:
        mgr = get_job_manager()
        progress = _Progress()

        async def run() -> _Result:
            progress.scanned = 42
            return _Result(doubled=0)

        record = await mgr.start(_Params(), run, progress=progress)
        assert record.progress is progress
        for _ in range(200):
            if mgr.current().state != JobState.running:
                break
            await asyncio.sleep(0.01)
        assert mgr.current().progress.model_dump() == {"scanned": 42}

    asyncio.run(scenario())


def test_manager_rejects_concurrent_start() -> None:
    async def scenario() -> None:
        mgr = get_job_manager()

        async def slow() -> _Result:
            await asyncio.sleep(0.5)
            return _Result(doubled=0)

        await mgr.start(_Params(), slow)
        with pytest.raises(JobAlreadyRunningError):
            await mgr.start(_Params(), slow)

    asyncio.run(scenario())
