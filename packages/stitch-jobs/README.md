# stitch-jobs

Shared **"FastAPI wrapper around a terminating process"** framework for Stitch
non-core services.

A service supplies a `run_fn(params) -> result` coroutine and gets:

- `POST /start` — launch the work in the background; returns immediately with a
  `job_id` (`202`), or joins an existing matching run (`200`).
- `GET /status/{job_id}` — poll the job's state and, once finished, its result.
- `GET /jobs` — list recent runs, newest first.

## Deduplication ("the same request across users")

Whether two requests are "the same" is a **per-service policy**:

- `SingletonPolicy` — one job at a time, regardless of params.
- `FingerprintPolicy(exclude={"payload_limit"})` — same job unless meaningful
  params differ (here a run capped at 500 and one at 501 collapse into one).
- `CallablePolicy(fn)` / `NoDedupPolicy` — custom, or never dedupe.

`JobManager(recent_within=...)` controls how long after a run finishes a new
identical request reuses it (so callers see results instead of re-running).

## Usage

```python
from stitch.jobs import JobManager, FingerprintPolicy, make_job_router

manager = JobManager(
    run_etl,                      # async (params) -> result
    policy=FingerprintPolicy(exclude={"payload_limit"}),
    recent_within=timedelta(minutes=5),
)
router = make_job_router(
    manager,
    params_model=EtlParams,        # request body + dedup params
    result_model=EtlResult,
    dependencies=[Depends(require_permissions(SOURCE_WRITE))],
    initiated_by=current_user_label,
)
# /start gains a `force` field automatically (force=True by default); set it to
# bypass dedup. The router strips `force` before computing the dedup key.
```

## Scope

The default `InMemoryJobStore` is single-replica and loses state on restart.
The `JobStore` protocol is the seam for a future DB-backed store; the manager
and routers are unaffected by that swap.
