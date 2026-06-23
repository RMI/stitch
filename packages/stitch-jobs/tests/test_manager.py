from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel

from stitch.jobs import (
    FingerprintPolicy,
    InMemoryJobStore,
    JobManager,
    JobState,
    NoDedupPolicy,
    SingletonPolicy,
)


class Params(BaseModel):
    name: str
    payload_limit: int | None = None


class Result(BaseModel):
    value: int


async def _wait_until_terminal(manager: JobManager, job_id: str, *, timeout=2.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        record = await manager.get(job_id)
        if record is not None and record.is_terminal:
            return record
        await asyncio.sleep(0.005)
    raise AssertionError("job did not reach a terminal state in time")


@pytest.mark.anyio
async def test_start_runs_and_succeeds() -> None:
    async def run(params: Params) -> Result:
        return Result(value=len(params.name))

    manager: JobManager[Params, Result] = JobManager(run, policy=SingletonPolicy())
    record, created = await manager.start(Params(name="alpha"), initiated_by="Tester")

    assert created is True
    assert record.state == JobState.running
    assert record.initiated_by == "Tester"

    final = await _wait_until_terminal(manager, record.job_id)
    assert final.state == JobState.succeeded
    assert final.result == Result(value=5)
    assert final.error is None
    assert final.finished_at is not None


@pytest.mark.anyio
async def test_failure_is_captured_in_record() -> None:
    async def run(params: Params) -> Result:
        raise RuntimeError("boom")

    manager: JobManager[Params, Result] = JobManager(run)
    record, _ = await manager.start(Params(name="x"))

    final = await _wait_until_terminal(manager, record.job_id)
    assert final.state == JobState.failed
    assert final.error == "boom"
    assert final.result is None


@pytest.mark.anyio
async def test_singleton_joins_active_run() -> None:
    release = asyncio.Event()

    async def run(params: Params) -> Result:
        await release.wait()
        return Result(value=1)

    manager: JobManager[Params, Result] = JobManager(run, policy=SingletonPolicy())
    first, first_created = await manager.start(Params(name="a"))
    second, second_created = await manager.start(Params(name="b"))

    assert first_created is True
    # Different params, but singleton policy → same active job is returned.
    assert second_created is False
    assert second.job_id == first.job_id

    release.set()
    await _wait_until_terminal(manager, first.job_id)


@pytest.mark.anyio
async def test_fingerprint_splits_by_params() -> None:
    release = asyncio.Event()

    async def run(params: Params) -> Result:
        await release.wait()
        return Result(value=1)

    manager: JobManager[Params, Result] = JobManager(run, policy=FingerprintPolicy())
    a, a_created = await manager.start(Params(name="a"))
    b, b_created = await manager.start(Params(name="b"))
    a_again, a_again_created = await manager.start(Params(name="a"))

    assert a_created and b_created
    assert a.job_id != b.job_id  # different params → independent jobs
    assert a_again_created is False  # identical params → joins the active 'a' run
    assert a_again.job_id == a.job_id

    release.set()
    await _wait_until_terminal(manager, a.job_id)
    await _wait_until_terminal(manager, b.job_id)


@pytest.mark.anyio
async def test_fingerprint_exclude_collapses_ignored_fields() -> None:
    release = asyncio.Event()

    async def run(params: Params) -> Result:
        await release.wait()
        return Result(value=1)

    manager: JobManager[Params, Result] = JobManager(
        run, policy=FingerprintPolicy(exclude={"payload_limit"})
    )
    first, first_created = await manager.start(Params(name="gem", payload_limit=500))
    second, second_created = await manager.start(Params(name="gem", payload_limit=501))

    # payload_limit excluded from the key → 500 and 501 are "the same" job.
    assert first_created is True
    assert second_created is False
    assert second.job_id == first.job_id

    release.set()
    await _wait_until_terminal(manager, first.job_id)


@pytest.mark.anyio
async def test_recent_completed_run_is_reused_within_window() -> None:
    now = {"t": datetime(2026, 1, 1, tzinfo=UTC)}

    def clock() -> datetime:
        return now["t"]

    async def run(params: Params) -> Result:
        return Result(value=1)

    store = InMemoryJobStore(clock=clock, retention=timedelta(hours=1))
    manager: JobManager[Params, Result] = JobManager(
        run,
        store=store,
        policy=FingerprintPolicy(),
        recent_within=timedelta(minutes=5),
        clock=clock,
    )

    first, _ = await manager.start(Params(name="a"))
    final = await _wait_until_terminal(manager, first.job_id)
    assert final.state == JobState.succeeded

    # Two minutes later: identical request reuses the just-finished run.
    now["t"] = now["t"] + timedelta(minutes=2)
    reused, created = await manager.start(Params(name="a"))
    assert created is False
    assert reused.job_id == first.job_id

    # Ten minutes after that: outside the window → a fresh run starts.
    now["t"] = now["t"] + timedelta(minutes=10)
    fresh, created = await manager.start(Params(name="a"))
    assert created is True
    assert fresh.job_id != first.job_id
    await _wait_until_terminal(manager, fresh.job_id)


@pytest.mark.anyio
async def test_force_bypasses_an_active_run() -> None:
    release = asyncio.Event()

    async def run(params: Params) -> Result:
        await release.wait()
        return Result(value=1)

    manager: JobManager[Params, Result] = JobManager(run, policy=SingletonPolicy())
    first, first_created = await manager.start(Params(name="a"))
    forced, forced_created = await manager.start(Params(name="a"), force=True)

    assert first_created is True
    assert forced_created is True  # force ignores the active run
    assert forced.job_id != first.job_id

    release.set()
    await _wait_until_terminal(manager, first.job_id)
    await _wait_until_terminal(manager, forced.job_id)


@pytest.mark.anyio
async def test_recent_within_none_reuses_indefinitely() -> None:
    now = {"t": datetime(2026, 1, 1, tzinfo=UTC)}

    def clock() -> datetime:
        return now["t"]

    async def run(params: Params) -> Result:
        return Result(value=1)

    store = InMemoryJobStore(clock=clock, retention=None)
    manager: JobManager[Params, Result] = JobManager(
        run,
        store=store,
        policy=FingerprintPolicy(),
        recent_within=None,
        clock=clock,
    )

    first, _ = await manager.start(Params(name="a"))
    await _wait_until_terminal(manager, first.job_id)

    # A year later, the same params still reuse the original run.
    now["t"] = now["t"] + timedelta(days=365)
    reused, created = await manager.start(Params(name="a"))
    assert created is False
    assert reused.job_id == first.job_id


@pytest.mark.anyio
async def test_failed_runs_are_not_reused_when_reuse_failed_false() -> None:
    calls = {"n": 0}

    async def run(params: Params) -> Result:
        calls["n"] += 1
        raise RuntimeError("boom")

    manager: JobManager[Params, Result] = JobManager(
        run,
        policy=FingerprintPolicy(),
        recent_within=None,
        reuse_failed=False,
    )

    first, first_created = await manager.start(Params(name="a"))
    await _wait_until_terminal(manager, first.job_id)
    assert first_created is True

    # The failed run is not reused — the next request retries with a new job.
    second, second_created = await manager.start(Params(name="a"))
    assert second_created is True
    assert second.job_id != first.job_id
    await _wait_until_terminal(manager, second.job_id)
    assert calls["n"] == 2


@pytest.mark.anyio
async def test_succeeded_runs_reused_even_when_reuse_failed_false() -> None:
    async def run(params: Params) -> Result:
        return Result(value=1)

    manager: JobManager[Params, Result] = JobManager(
        run,
        policy=FingerprintPolicy(),
        recent_within=None,
        reuse_failed=False,
    )

    first, _ = await manager.start(Params(name="a"))
    await _wait_until_terminal(manager, first.job_id)

    reused, created = await manager.start(Params(name="a"))
    assert created is False
    assert reused.job_id == first.job_id


@pytest.mark.anyio
async def test_list_for_params_returns_only_matching_key_newest_first() -> None:
    async def run(params: Params) -> Result:
        return Result(value=1)

    manager: JobManager[Params, Result] = JobManager(
        run, policy=FingerprintPolicy(), recent_within=None
    )
    a, _ = await manager.start(Params(name="a"))
    await _wait_until_terminal(manager, a.job_id)
    b, _ = await manager.start(Params(name="b"))
    await _wait_until_terminal(manager, b.job_id)
    a2, _ = await manager.start(Params(name="a"), force=True)
    await _wait_until_terminal(manager, a2.job_id)

    runs = await manager.list_for_params(Params(name="a"))
    assert [r.job_id for r in runs] == [a2.job_id, a.job_id]  # newest first, no "b"


@pytest.mark.anyio
async def test_list_for_params_empty_when_policy_opts_out() -> None:
    async def run(params: Params) -> Result:
        return Result(value=1)

    manager: JobManager[Params, Result] = JobManager(run, policy=NoDedupPolicy())
    record, _ = await manager.start(Params(name="a"))
    await _wait_until_terminal(manager, record.job_id)

    assert await manager.list_for_params(Params(name="a")) == []


@pytest.mark.anyio
async def test_terminal_records_evicted_after_retention() -> None:
    now = {"t": datetime(2026, 1, 1, tzinfo=UTC)}

    def clock() -> datetime:
        return now["t"]

    async def run(params: Params) -> Result:
        return Result(value=1)

    store = InMemoryJobStore(clock=clock, retention=timedelta(minutes=30))
    manager: JobManager[Params, Result] = JobManager(run, store=store, clock=clock)

    record, _ = await manager.start(Params(name="a"))
    await _wait_until_terminal(manager, record.job_id)

    now["t"] = now["t"] + timedelta(hours=1)
    assert await manager.get(record.job_id) is None
