from __future__ import annotations

from datetime import timedelta

from fastapi import Depends
from pydantic import Field
from stitch.auth.permissions import SERVICE_ENTITY_LINKAGE_RUN
from stitch.jobs import (
    FingerprintPolicy,
    InMemoryJobStore,
    JobManager,
    make_job_router,
)

from stitch.entity_linkage.auth import initiated_by, require_permissions
from stitch.entity_linkage.linkage import LinkageParams, LinkageResult, run_linkage

# Two requests are "the same" run when all tunable params match. Identical
# requests (same paging + apply_merges) collapse onto one job — so a second
# user sees the in-flight run, and reuses its result for `recent_within` after
# it finishes — while different params run independently.
# Reuse an identical run for 24h. Retention must cover the reuse window, else
# terminal records would be evicted before they could be reused.
_REUSE_WINDOW = timedelta(hours=24)
_manager: JobManager[LinkageParams, LinkageResult] = JobManager(
    run_linkage,
    policy=FingerprintPolicy(),
    recent_within=_REUSE_WINDOW,
    store=InMemoryJobStore(retention=_REUSE_WINDOW),
)


def get_job_manager() -> JobManager[LinkageParams, LinkageResult]:
    return _manager


class StartLinkageRequest(LinkageParams):
    force: bool = Field(
        default=False,
        description="Re-run even if a recent identical run exists.",
    )


def _to_params(request: StartLinkageRequest) -> LinkageParams:
    # `force` is dropped here so it never participates in the dedup key.
    return LinkageParams(**request.model_dump(exclude={"force"}))


router = make_job_router(
    _manager,
    start_request_model=StartLinkageRequest,
    params_model=LinkageParams,
    to_params=_to_params,
    force_attr="force",
    result_model=LinkageResult,
    dependencies=[Depends(require_permissions(SERVICE_ENTITY_LINKAGE_RUN))],
    initiated_by=initiated_by,
    tags=["entity-linkage"],
)
