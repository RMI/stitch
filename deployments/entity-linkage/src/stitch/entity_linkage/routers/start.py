from __future__ import annotations

from datetime import timedelta

from fastapi import Depends
from stitch.auth.permissions import SERVICE_ENTITY_LINKAGE_RUN
from stitch.jobs import FingerprintPolicy, JobManager, make_job_router

from stitch.entity_linkage.auth import AuthContext, require_permissions
from stitch.entity_linkage.entities import User
from stitch.entity_linkage.linkage import LinkageParams, LinkageResult, run_linkage

# Two requests are "the same" run when all tunable params match. Identical
# requests (same paging + apply_merges) collapse onto one job — so a second
# user sees the in-flight run, and reuses its result for `recent_within` after
# it finishes — while different params run independently.
_manager: JobManager[LinkageParams, LinkageResult] = JobManager(
    run_linkage,
    policy=FingerprintPolicy(),
    recent_within=timedelta(minutes=5),
)


def get_job_manager() -> JobManager[LinkageParams, LinkageResult]:
    return _manager


def _extract_user_label(user: User) -> str:
    return user.name or user.email or user.sub


async def initiated_by(auth_context: AuthContext) -> str:
    return _extract_user_label(auth_context.user)


router = make_job_router(
    _manager,
    start_request_model=LinkageParams,
    result_model=LinkageResult,
    dependencies=[Depends(require_permissions(SERVICE_ENTITY_LINKAGE_RUN))],
    initiated_by=initiated_by,
    tags=["entity-linkage"],
)
