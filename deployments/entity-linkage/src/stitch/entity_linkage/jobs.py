"""In-memory background-job manager for the bulk linkage pass.

Borrowed from the ETL-POC (`stitch.etl.jobs`): a single-job, in-memory run
manager. The linkage pass over a production-scale dataset is long-running, so it
runs as a background task and is polled for status rather than blocking the
request.

Limitations (inherited, and acceptable while entity-linkage runs a single
uvicorn worker): state is lost on restart, only one run is tracked at a time,
and the record lives in the worker process that started it -- so this must move
to shared storage (Redis/DB) before the service is scaled to multiple workers.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, SerializeAsAny

logger = logging.getLogger("stitch.entity_linkage")

RunThunk = Callable[[], Awaitable[BaseModel]]


class JobState(str, Enum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class JobRecord(BaseModel):
    job_id: str
    state: JobState
    params: SerializeAsAny[BaseModel]
    started_at: datetime
    finished_at: datetime | None = None
    result: SerializeAsAny[BaseModel] | None = None
    error: str | None = None


class JobAlreadyRunningError(Exception):
    def __init__(self, job_id: str):
        self.job_id = job_id
        super().__init__(f"A job is already running: {job_id}")


def format_exception(exc: BaseException) -> str:
    """Describe ``exc`` in a string that is never empty.

    ``str(exc)`` alone is not enough: httpx's timeout exceptions
    (``ReadTimeout``, ``ConnectTimeout``, ``PoolTimeout``) carry an empty
    message, so a run that died on one recorded a blank ``error`` and the only
    way to learn what had happened was the container logs.
    """
    message = str(exc)
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


class JobManager:
    """Single-job, in-memory run manager.

    State is lost on restart and concurrent runs are rejected. The run body is
    supplied per start as a zero-arg coroutine, so this manager is generic.
    """

    def __init__(self) -> None:
        self._record: JobRecord | None = None
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    def current(self) -> JobRecord | None:
        return self._record

    async def start(self, params: BaseModel, run: RunThunk) -> JobRecord:
        async with self._lock:
            if self._record is not None and self._record.state == JobState.running:
                raise JobAlreadyRunningError(self._record.job_id)

            record = JobRecord(
                job_id=str(uuid4()),
                state=JobState.running,
                params=params,
                started_at=datetime.now(UTC),
            )
            self._record = record
            self._task = asyncio.create_task(self._run(record, run))
            return record

    async def _run(self, record: JobRecord, run: RunThunk) -> None:
        try:
            record.result = await run()
            record.state = JobState.succeeded
        except Exception as exc:
            logger.exception("Linkage run %s failed", record.job_id)
            record.error = format_exception(exc)
            record.state = JobState.failed
        finally:
            record.finished_at = datetime.now(UTC)


_manager: JobManager | None = None


def get_job_manager() -> JobManager:
    """Return the process-wide linkage job manager (single linkage key)."""
    global _manager
    if _manager is None:
        _manager = JobManager()
    return _manager


def reset_manager() -> None:
    """Drop the manager. Test-only; not part of the request flow."""
    global _manager
    _manager = None
