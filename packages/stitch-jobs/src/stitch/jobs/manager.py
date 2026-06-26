from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Generic
from uuid import uuid4

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import Link, SpanContext, SpanKind, Status, StatusCode

from .models import P, R, JobRecord, JobState
from .store import InMemoryJobStore, JobStore
from .uniqueness import SingletonPolicy, UniquenessPolicy

logger = logging.getLogger("stitch.jobs")

# No-op when no provider is configured (tracing disabled), so jobs behave
# identically whether or not the host service has tracing on.
_tracer = trace.get_tracer("stitch.jobs")

#: Terminal states that, by default, an existing run may be reused from.
_DEFAULT_REUSABLE_TERMINAL = frozenset({JobState.succeeded, JobState.failed})


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

    Reuse is tunable:
      - ``recent_within`` — how long after finishing a terminal run stays
        reusable. ``None`` means forever (no expiry).
      - ``reuse_failed`` — when ``False``, failed runs are kept/visible but are
        not reused, so the next request retries (transient failures self-heal).
      - ``start(force=True)`` — bypass reuse entirely and always launch a new run.
    """

    def __init__(
        self,
        run_fn: Callable[[P], Awaitable[R]],
        *,
        store: JobStore | None = None,
        policy: UniquenessPolicy | None = None,
        recent_within: timedelta | None = timedelta(0),
        reuse_failed: bool = True,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._run_fn = run_fn
        self._store: JobStore = store or InMemoryJobStore(clock=clock)
        self._policy = policy or SingletonPolicy()
        self._recent_within = recent_within
        self._reusable_states = frozenset({JobState.running}) | (
            _DEFAULT_REUSABLE_TERMINAL
            if reuse_failed
            else frozenset({JobState.succeeded})
        )
        self._clock = clock
        self._lock = asyncio.Lock()
        # Hold strong refs so tasks aren't garbage-collected mid-flight.
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(
        self, params: P, *, initiated_by: str | None = None, force: bool = False
    ) -> tuple[JobRecord[P, R], bool]:
        """Start a run, or join an existing matching one.

        Returns ``(record, created)`` where ``created`` is ``False`` when an
        existing active/recent run with the same dedup key was returned instead
        of launching a new task. ``force=True`` always launches a new run.
        """
        async with self._lock:
            key = self._policy.key(params)
            if not force and key is not None:
                existing = await self._store.find_active_or_recent(
                    key,
                    recent_within=self._recent_within,
                    reusable_states=self._reusable_states,
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
            # Capture the triggering request's span so the (detached) job run can
            # link back to it without nesting under an already-finished request.
            trigger = trace.get_current_span().get_span_context()
            task = asyncio.create_task(self._run(record, params, trigger))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return record, True

    async def _run(
        self, record: JobRecord[P, R], params: P, trigger: SpanContext | None = None
    ) -> None:
        links = [Link(trigger)] if trigger is not None and trigger.is_valid else None
        # New root span (empty parent context) so a reused/decoupled job isn't
        # buried under one caller's request; the link makes it navigable from the
        # trigger. No-op span when tracing is disabled.
        with _tracer.start_as_current_span(
            "job.run",
            context=otel_context.Context(),
            kind=SpanKind.INTERNAL,
            links=links,
        ) as span:
            span.set_attribute("stitch.job.id", record.job_id)
            if record.dedup_key is not None:
                span.set_attribute("stitch.job.dedup_key", record.dedup_key)
            if record.initiated_by is not None:
                span.set_attribute("stitch.job.initiated_by", record.initiated_by)
            try:
                record.result = await self._run_fn(params)
                record.state = JobState.succeeded
            except Exception as exc:
                # Broad on purpose: any run_fn failure is captured onto the record
                # (state=failed, error set) rather than crashing the background task.
                logger.exception("job %s failed", record.job_id)
                record.error = str(exc)
                record.state = JobState.failed
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.record_exception(exc)
            finally:
                record.finished_at = self._clock()
                span.set_attribute("stitch.job.state", record.state.value)

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

    async def list_for_params(
        self, params: P, *, limit: int | None = None
    ) -> list[JobRecord[P, R]]:
        """Return runs whose dedup key matches ``params``, newest first.

        Lets a caller discover the runs for a specific request (e.g. a given
        resource/field) without scanning the whole job list — the server
        applies the same uniqueness policy used for dedup, so there is no
        client/server filter drift. Returns ``[]`` when the policy opts the
        params out of deduplication (no stable key).
        """
        key = self._policy.key(params)
        if key is None:
            return []
        return await self._store.list_by_key(key, limit=limit)
