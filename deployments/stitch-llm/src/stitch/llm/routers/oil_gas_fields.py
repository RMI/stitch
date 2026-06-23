from __future__ import annotations

from fastapi import APIRouter, Depends
from stitch.auth.permissions import SERVICE_LLM_SUGGEST
from stitch.jobs import FingerprintPolicy, InMemoryJobStore, JobManager, make_job_router

from stitch.llm.auth import initiated_by, require_permissions
from stitch.llm.entities import FieldSuggestionResponse
from stitch.llm.jobs import FieldSuggestionParams, run_suggestion

# Suggestions are tracked per (resource_id, field) with no expiry: once a pair
# has a result it is reused indefinitely (decoupled from the original caller, so
# a later user sees that a backfill was attempted). Failed runs are kept/visible
# but not reused, so the next request retries; `force` bypasses reuse entirely.
_manager: JobManager[FieldSuggestionParams, FieldSuggestionResponse] = JobManager(
    run_suggestion,
    policy=FingerprintPolicy(),
    recent_within=None,
    reuse_failed=False,
    store=InMemoryJobStore(retention=None),
)


def get_job_manager() -> JobManager[FieldSuggestionParams, FieldSuggestionResponse]:
    return _manager


_job_router = make_job_router(
    _manager,
    params_model=FieldSuggestionParams,
    result_model=FieldSuggestionResponse,
    dependencies=[Depends(require_permissions(SERVICE_LLM_SUGGEST))],
    initiated_by=initiated_by,
    tags=["oil_gas_fields"],
)

# Namespace the job endpoints under /oil-gas-fields (→ /api/v1/oil-gas-fields/start, …).
router = APIRouter(prefix="/oil-gas-fields")
router.include_router(_job_router)
