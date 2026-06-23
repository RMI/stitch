from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from stitch.auth.permissions import SERVICE_LLM_SUGGEST
from stitch.jobs import FingerprintPolicy, InMemoryJobStore, JobManager, make_job_router

from stitch.llm.auth import AuthContext, require_permissions
from stitch.llm.entities import FieldSuggestionResponse, User
from stitch.llm.jobs import (
    AllowedSuggestionField,
    FieldSuggestionParams,
    run_suggestion,
)

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


class StartSuggestionRequest(BaseModel):
    resource_id: int
    field: AllowedSuggestionField
    force: bool = Field(
        default=False,
        description="Re-run even if a suggestion for this (resource, field) exists.",
    )


def _to_params(request: StartSuggestionRequest) -> FieldSuggestionParams:
    # `force` is intentionally dropped so it never participates in the dedup key.
    return FieldSuggestionParams(resource_id=request.resource_id, field=request.field)


def _extract_user_label(user: User) -> str:
    return user.name or user.email or user.sub


async def initiated_by(auth_context: AuthContext) -> str:
    return _extract_user_label(auth_context.user)


_job_router = make_job_router(
    _manager,
    start_request_model=StartSuggestionRequest,
    params_model=FieldSuggestionParams,
    to_params=_to_params,
    force_attr="force",
    result_model=FieldSuggestionResponse,
    dependencies=[Depends(require_permissions(SERVICE_LLM_SUGGEST))],
    initiated_by=initiated_by,
    tags=["oil_gas_fields"],
)

# Namespace the job endpoints under /oil-gas-fields (→ /api/v1/oil-gas-fields/start, …).
router = APIRouter(prefix="/oil-gas-fields")
router.include_router(_job_router)
