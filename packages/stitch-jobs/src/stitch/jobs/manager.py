from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Generic
from uuid import uuid4

from .models import P, R, JobRecord, JobState
from .store import InMemoryJobStore, JobStore
from .uniqueness import SingletonPolicy, UniquenessPolicy

logger = logging.getLogger("stitch.jobs")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class JobManager(Generic[P, R]):
    """Runs a terminating process as a background job and tracks its state.

    Wraps a ``run_fn(params) -> result`` coroutine. ``start()`` launches it as
    an ``asyncio.Task`` and returns immediately; the record's state transitions
    ``running -> succeeded|failed`` as the task completes. Callers observe
    progress via :meth:`get` / :meth:`list` (exposed over HTTP by
    :func:`stitch.jobs.routers.make_job_router`).

    Deduplication is governed by the injected :class:`UniquenessPolicy`: before
    starting, the manager looks for an existing run with the same key that is
    still active — or finished within ``recent_within`` — and returns it instead
    of starting a duplicate. That is what lets a second user observe (and reuse
    the results of) a run another user already kicked off.
    """

    def __init__(
        self,
        run_fn: Callable[[P], Awaitable[R]],
        *,
        store: JobStore | None = None,
        policy: UniquenessPolicy | None = None,
        recent_within: timedelta = timedelta(0),
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._run_fn = run_fn
        self._store: JobStore = store or InMemoryJobStore(clock=clock)
        self._policy = policy or SingletonPolicy()
        self._recent_within = recent_within
        self._clock = clock
        self._lock = asyncio.Lock()
        # Hold strong refs so tasks aren't garbage-collected mid-flight.
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(
        self, params: P, *, initiated_by: str | None = None
    ) -> tuple[JobRecord[P, R], bool]:
        """Start a run, or join an existing matching one.

        Returns ``(record, created)`` where ``created`` is ``False`` when an
        existing active/recent run with the same dedup key was returned instead
        of launching a new task.
        """
        async with self._lock:
            key = self._policy.key(params)
            if key is not None:
                existing = await self._store.find_active_or_recent(
                    key, recent_within=self._recent_within
                )
                if existing is not None:
                    return existing, False

            record: JobRecord[P, R] = JobRecord(
                job_id=str(uuid4()),
                state=JobState.running,
                dedup_key=key,
                initiated_by=initiated_by,
                params=params,
                started_at=self._clock(),
            )
            await self._store.create(record)
            task = asyncio.create_task(self._run(record, params))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return record, True

    async def _run(self, record: JobRecord[P, R], params: P) -> None:
        try:
            record.result = await self._run_fn(params)
            record.state = JobState.succeeded
        except Exception as exc:  # noqa: BLE001 - captured into the record
            logger.exception("job %s failed", record.job_id)
            record.error = str(exc)
            record.state = JobState.failed
        finally:
            record.finished_at = self._clock()

    def reset(self) -> None:
        """Cancel in-flight tasks and drop all run state.

        For tests that share a module-level manager; not part of the request
        flow.
        """
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        clear = getattr(self._store, "clear", None)
        if callable(clear):
            clear()

    async def get(self, job_id: str) -> JobRecord[P, R] | None:
        return await self._store.get(job_id)

    async def list(self, *, limit: int | None = None) -> list[JobRecord[P, R]]:
        return await self._store.list(limit=limit)
