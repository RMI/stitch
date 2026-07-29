# entity-linkage

Basic Entity linkage service.

Matches resources on normalized (case-insensitive, whitespace-trimmed) name and
country, and proposes them to the Stitch API as merge candidates.

## Endpoints

- `POST /api/v1/oil-gas-fields/{id}/link` — link a single resource against its
  duplicates in bounded memory: fetch its detail, search the API for same-name
  candidates, confirm same country, and (when `apply_merges` is true) submit the
  merge candidate. Synchronous. This is the unit of work the bulk pass iterates,
  and the natural task a queue would enqueue.
- `POST /api/v1/oil-gas-fields/link` — launch a **background** linkage pass over
  every resource, streaming the list one page at a time. Returns `202 Accepted`
  with a `job_id` immediately; a second start while one is running returns `409`.
  Replaces the in-memory `/start` pass for production-scale datasets.
- `GET /api/v1/oil-gas-fields/link/status` — poll the most recent pass: its
  `state` (`running`/`succeeded`/`failed`), and on success the `result` summary
  (resources scanned, match groups, candidates created/skipped). `404` before any
  run has started.
- `POST /api/v1/start` — the original whole-dataset in-memory pass. Superseded by
  the endpoints above and retained for now; it loads every resource into memory
  and fails at production scale.

Job state is in-memory and single-process (see `jobs.py`): it is lost on restart,
tracks one run at a time, and must move to shared storage before the service is
scaled beyond one worker.

All linkage endpoints require the `service:entity-linkage:run` permission and
default to a dry run (`apply_merges` defaults to `false`).

Downstream Stitch API auth is provided through `STITCH_CLIENT_BEARER_TOKEN`.
