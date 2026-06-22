from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel

P = TypeVar("P", bound=BaseModel)
R = TypeVar("R", bound=BaseModel)


class JobState(str, Enum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


#: States a job can no longer leave.
TERMINAL_STATES: frozenset[JobState] = frozenset({JobState.succeeded, JobState.failed})


class JobRecord(BaseModel, Generic[P, R]):
    """The full, observable state of a single job run.

    Generic over the per-service ``params`` and ``result`` Pydantic models so a
    service gets typed request params and typed results in its OpenAPI schema.

    Records are mutated in place by :class:`~stitch.jobs.manager.JobManager` as
    the run progresses (``state``/``result``/``error``/``finished_at``).
    """

    job_id: str
    state: JobState
    #: Per-service uniqueness key; ``None`` when the job is not deduplicated.
    dedup_key: str | None = None
    #: Human label of the user who first started the run (best-effort).
    initiated_by: str | None = None
    params: P
    started_at: datetime
    finished_at: datetime | None = None
    result: R | None = None
    error: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES
