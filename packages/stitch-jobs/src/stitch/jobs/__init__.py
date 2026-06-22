"""Shared FastAPI job framework for Stitch non-core services.

Wraps a terminating process (``run_fn(params) -> result``) with a ``/start``
endpoint, a ``/status`` poll, and a ``/jobs`` listing, plus per-service
deduplication so a request can be observed/reused across users.
"""

from .manager import JobManager
from .models import TERMINAL_STATES, JobRecord, JobState
from .routers import make_job_router
from .store import InMemoryJobStore, JobStore
from .uniqueness import (
    CallablePolicy,
    FingerprintPolicy,
    NoDedupPolicy,
    SingletonPolicy,
    UniquenessPolicy,
)

__all__ = [
    "TERMINAL_STATES",
    "CallablePolicy",
    "FingerprintPolicy",
    "InMemoryJobStore",
    "JobManager",
    "JobRecord",
    "JobState",
    "JobStore",
    "NoDedupPolicy",
    "SingletonPolicy",
    "UniquenessPolicy",
    "make_job_router",
]
