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
- `GET /api/v1/oil-gas-fields/link/status` — poll the most recent pass: its
  `state` (`running`/`succeeded`/`failed`), and on success the `result` summary
  (resources scanned, match groups, candidates created/skipped). `404` before any
  run has started.

While a pass is running, `status` also reports `progress` — resources scanned,
match groups found, and candidates created/skipped so far. The same counters are
written to the logs as a `linkage_progress` event every 100 resources, so a run's
throughput (and how far a failed run got) is visible without polling.

Job state is in-memory and single-process (see `jobs.py`): it is lost on restart,
tracks one run at a time, and must move to shared storage before the service is
scaled beyond one worker.

## Downstream requests

A full pass makes a very large number of calls to the Stitch API, so a single
transient failure would otherwise end the whole run. Reads are retried with
exponential backoff and jitter; writes are never replayed, since a timed-out
create may already have been applied.

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENTITY_LINKAGE_API_TIMEOUT_SECONDS` | `30` | How long to wait on one request |
| `ENTITY_LINKAGE_API_MAX_RETRIES` | `2` | Retries after a failed read; `0` disables |

Raising the timeout is an operational lever, not a fix: if the downstream query
is genuinely slow, a longer timeout makes an already-long pass longer. The
underlying cost is the substring name search the matcher relies on (STIT-573).

All linkage endpoints require the `service:entity-linkage:run` permission and
default to a dry run (`apply_merges` defaults to `false`).

Downstream Stitch API auth is provided through `STITCH_CLIENT_BEARER_TOKEN`.
