from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from .models import JobRecord, JobState


def _utcnow() -> datetime:
    return datetime.now(UTC)


class JobStore(Protocol):
    """Persistence seam for job records.

    The in-memory implementation below is sufficient for a single replica. A
    DB-backed store (surviving restarts and shared across replicas) can be
    dropped in later behind this same interface without touching the manager or
    routers.
    """

    async def create(self, record: JobRecord) -> None:
        """Persist a newly started job record."""

    async def get(self, job_id: str) -> JobRecord | None:
        """Return the record for ``job_id``, or ``None`` if unknown."""

    async def find_active_or_recent(
        self, dedup_key: str, *, recent_within: timedelta
    ) -> JobRecord | None:
        """Return a matching job that is running or finished recently."""

    async def list(self, *, limit: int | None = None) -> list[JobRecord]:
        """Return recent records, newest first."""

    def clear(self) -> None:
        """Drop all records (test affordance)."""


class InMemoryJobStore:
    """Process-local job store backed by a dict.

    Completed records are retained so a just-finished run is still discoverable
    (for cross-user result reuse and ``GET /status``), then evicted once older
    than ``retention``. State is lost on restart and is not shared across
    replicas — acceptable for the current single-replica deployments.
    """

    def __init__(
        self,
        *,
        retention: timedelta | None = timedelta(hours=1),
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._records: dict[str, JobRecord] = {}
        self._retention = retention
        self._clock = clock

    def _evict_expired(self) -> None:
        if self._retention is None:
            return
        cutoff = self._clock() - self._retention
        stale = [
            job_id
            for job_id, record in self._records.items()
            if record.finished_at is not None and record.finished_at < cutoff
        ]
        for job_id in stale:
            del self._records[job_id]

    async def create(self, record: JobRecord) -> None:
        self._evict_expired()
        self._records[record.job_id] = record

    async def get(self, job_id: str) -> JobRecord | None:
        self._evict_expired()
        return self._records.get(job_id)

    async def find_active_or_recent(
        self, dedup_key: str, *, recent_within: timedelta
    ) -> JobRecord | None:
        """Return the newest matching job that is still running, or that
        finished within ``recent_within``. Newest-first so callers join/observe
        the most relevant run.
        """
        self._evict_expired()
        now = self._clock()
        candidates = [
            record
            for record in self._records.values()
            if record.dedup_key == dedup_key
            and (
                record.state == JobState.running
                or (
                    record.finished_at is not None
                    and now - record.finished_at <= recent_within
                )
            )
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda record: record.started_at)

    def clear(self) -> None:
        """Drop all records. For tests; not part of the request flow."""
        self._records.clear()

    async def list(self, *, limit: int | None = None) -> list[JobRecord]:
        self._evict_expired()
        records = sorted(
            self._records.values(),
            key=lambda record: record.started_at,
            reverse=True,
        )
        if limit is not None:
            records = records[:limit]
        return records
