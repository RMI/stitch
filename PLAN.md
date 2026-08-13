# Low-priority request lane for Entity Linkage

## Context

Entity Linkage (EL) calls the same public API surface as the frontend. That is a
genuinely good programming model and this plan keeps it. The problem is that when
a linkage run is in flight it saturates the shared dev API, leaving too little
capacity for a human to use the app.

**Direct answer to the question that prompted this: FastAPI/ASGI has no built-in
request priority.** There is no priority queue in uvicorn or Starlette, and
`asyncio` runs ready tasks in FIFO order. Priority has to be built as
*cooperative admission control*: the caller declares its intent and the server
chooses to make it wait.

Equally important, the obvious implementation — a concurrency semaphore — would
be a **no-op here**. EL's in-flight HTTP concurrency is already 1:
`JobManager` permits one run at a time
([jobs.py:67](deployments/entity-linkage/src/stitch/entity_linkage/jobs.py:67))
and `link_all` awaits every call sequentially
([matching.py:163](deployments/entity-linkage/src/stitch/entity_linkage/matching.py:163)).

EL saturates the API through **duty cycle and per-request cost**, not
parallelism. `find_match_group_for_resource` costs ~3+ requests per resource
(1 detail + ≥1 page of the `q=` ILIKE search + 1 detail per same-name
candidate), and the `q=` search on `GET /oil-gas-fields/` is the most expensive
query in the system — the per-request licensed-resource CTE called out in
[PERFORMANCE.md](deployments/PERFORMANCE.md). Across a run of R resources that is
`O(R)` back-to-back expensive requests with zero think time.

Where that lands, verified:

- **Not the DB pool.** At concurrency 1, EL holds 1–2 of the 15 available
  connections. The pool is not the constraint *for EL* (though it is undeclared
  and worth pinning — see Commit 4).
- **CPU, in two places.** The API container pins no `cpu`/`memory`, so it takes
  the Azure Container Apps default of ~0.5 vCPU. And every authenticated request
  pays an RSA signature verify in a thread
  ([auth.py:99](deployments/api/src/stitch/api/auth.py:99)) with no memoization,
  plus **two sequential DB checkouts** — `get_current_user` opens its own session
  and `COMMIT`s on every request, even pure reads
  ([auth.py:145](deployments/api/src/stitch/api/auth.py:145)) — before the
  handler's `UnitOfWork` runs the real query.

So the lever is "EL does less work per unit time when a human is present," and
gating in **middleware** (before dependency resolution) is what lets a deferred
request skip the RSA verify and both DB checkouts.

### Success criterion

With a linkage run in progress against the dev stack, interactive request
latency on `GET /api/v1/oil-gas-fields/` stays close to its idle baseline, and
the linkage run still completes (no failed job, no client timeouts). With no
interactive traffic, EL runs at full speed.

### Decisions taken

- **Adaptive server-side gate.** Requests tagged as batch defer while
  interactive traffic is active; EL runs full speed on an idle server.
- **Dev/shared scope, prod-safe.** Behind a `Settings` flag, **default off**,
  enabled by env in dev/PR lanes. Production ships the code but not the
  behavior.
- **Separate commits.** Four independent commits, each reviewable and revertible
  on its own. Not one shot. Commits 1 and 2 are the minimum viable pair — the gate
  is inert until EL tags itself.

Why not prod-on by default: Container Apps autoscales on HTTP concurrency and
`max-replicas` is unset (platform default 10). A gate that makes requests *wait*
inflates in-flight concurrency — the very autoscale signal — so in production it
could trigger scale-out instead of backpressure. If this is ever promoted to
prod it should shed with 429 rather than wait. Dev lanes (`min-replicas: 1`,
single container) have no such feedback loop.

---

## Commit 1 — API: make batch traffic yield to interactive traffic

**New file:** `deployments/api/src/stitch/api/admission.py`

**Modified:** `deployments/api/src/stitch/api/middleware.py`,
`deployments/api/src/stitch/api/settings.py`, `env.example`

### Naming: "traffic class", not "priority"

**`priority` is already taken in this domain** and means something else
entirely: OGSI source ordering, where lower wins —
`SetFieldPriorityRequest` ([entities.py:163](deployments/api/src/stitch/api/entities.py:163)),
`OGFieldSourcePriority`, `source_priority`, and the
`/{id}/fields/{field}/sources/priority` route
([oil_gas_fields.py:294](deployments/api/src/stitch/api/routers/oil_gas_fields.py:294)).
Reusing the word for request scheduling would be actively confusing to a future
reader. So:

- Header: **`X-Stitch-Traffic-Class`**, values `interactive` (default) | `batch`.
  Matches the documented `X-Stitch-*` namespacing rule at
  [middleware.py:43](packages/stitch-observability/src/stitch/observability/middleware.py:43)
  and the `X-Stitch-Perf-Scenario` precedent
  ([middleware.py:101](packages/stitch-observability/src/stitch/observability/middleware.py:101)).
- Middleware: `BatchYieldMiddleware`.

No CORS change needed — this is a server-to-server header, and
`X-Stitch-Perf-Scenario` likewise is not in `ALLOWED_HEADERS`. (If the frontend
ever needed to send it, it would have to be added there.)

### Gate mechanics

**Classification.** Default is `interactive`. Only an explicit `batch` tag
downgrades a request, so spoofing is a non-issue — the worst a caller can do is
decline to mark itself, which is a cooperative-system property, not a security
hole. This also means classification needs no auth, which is exactly what lets a
deferred request skip the RSA verify and both DB checkouts.

**Must be pure ASGI, not `BaseHTTPMiddleware`.** Not a style preference — a
correctness requirement. `BaseHTTPMiddleware.call_next` returns as soon as
response *headers* are available; the body streams afterwards. A `try/finally`
around it would decrement the in-flight counter **too early**, releasing batch
traffic while an interactive response was still being sent. `await self.app(scope,
receive, send)` in a pure ASGI middleware returns only after the full response is
sent, which is exactly the definition of "in flight" we need. Pure ASGI also
avoids adding a task + task group + two memory object streams to every
*interactive* request — i.e. the traffic this change exists to speed up.

**Tracking interactive activity.** Both signals are required; each alone is
broken. Counter alone: interactive requests last tens of ms, so a poller would
usually observe zero even during active browsing. Timestamp alone: while a slow
interactive request is *in progress* the timestamp hasn't been updated yet, so the
window reads "quiet" and batch launches right on top of it.

- `in_flight: int` — incremented/decremented around `await self.app(...)` in a
  `try/finally`, so a handler exception, a 500, or a client disconnect
  (`CancelledError`) all release it. If this ever leaks, the gate wedges shut for
  the life of the process and every batch request pays the full `max_wait` —
  the highest-value invariant in the module, and worth a dedicated test.
- `last_finished_at: float` — `time.monotonic()`, stamped in the same `finally`.
  Initialized to `float("-inf")`, **not** `0.0`: `monotonic()`'s epoch is
  arbitrary, so "never seen" has to read as "infinitely long ago."

Quiet means `in_flight == 0` **and** `now - last_finished_at >= quiet_ms`. The
quiet window is what makes this work for a browser: a human's requests arrive in
bursts with gaps, and without it batch traffic slips back in between two clicks.

**Check first, then sleep — the ordering defines the semantics.** The loop tests
the quiet condition, and only sleeps if it fails:

- Idle server when a batch request arrives ⇒ admitted immediately, **zero added
  latency**. The poll interval is *not* a settling delay.
- Interactive request finishes at t=0 with a batch request already waiting ⇒ the
  condition turns true at `quiet_ms`, but the waiter only notices on its next
  tick, so it resumes between `quiet_ms` and `quiet_ms + poll interval`.
  **`quiet_ms` is the floor; the poll interval is overshoot above it, not an
  addend.** This is why the poll interval must stay well below `quiet_ms`.

The poll interval is a module constant (`_POLL_INTERVAL_S = 0.05`), deliberately
**not** a setting: it is an implementation detail of how precisely batch traffic
notices the window clear, exposing it invites reading it as an imposed delay, and
20 wakeups/sec on one task is noise. Polling rather than an `asyncio.Event`
because an event fired on `in_flight == 0` would still need a timer for the quiet
window — so it sleeps either way, and the loop is obviously correct on inspection.

**The gate is global, and blocks only at admission.** A single interactive
request in flight gates *all* batch traffic — not per-route, not per-caller.
Today that is academic (EL's concurrency is 1, so "all batch traffic" is one
request), but if seed/ETL/LLM later tag themselves batch they share one signal
and are released together. A batch request that has *already been admitted* is
never interrupted; see Risk 2.

**Bounded wait, then admit anyway — the gate never returns 429.** After
`max_wait_ms`, log a warning and let the request through. No shedding, no
`Retry-After`, nothing for a client to handle.

Two reasons this is the right call, not just the timid one:

- **Deferring is nearly free here.** Because the gate sits *before* dependency
  resolution, a waiting batch request holds one asyncio task and one TCP
  connection and **zero DB pool connections** — it has not reached
  `get_uow`/`get_current_user`. The usual argument for shedding ("stop holding
  resources") mostly evaporates.
- **It cannot fail a run.** Admitting makes the design *structurally incapable*
  of breaking entity-linkage, which is the right property for a default-off dev
  knob. An unbounded defer would instead surface as a client read timeout against
  the 30s client timeout
  ([async_client.py:44](packages/stitch-client/src/stitch/client/async_client.py:44));
  `max_wait_ms` defaults well under it.

**Exemptions — skip the gate AND the accounting.** `/api/v1/health` and
`/api/v1/health/details` bypass both, plus non-`http` scopes (`lifespan`) and
`OPTIONS` preflights. Two separate hazards:

1. *Never gate them.* The docker healthcheck hits `/api/v1/health` every 5s with a
   5s timeout ([docker-compose.yml:24](docker-compose.yml:24)), so a deferral
   would flap the container unhealthy. Worse, EL's own `wait_for_health` uses a
   **2s** per-request timeout
   ([async_client.py:57](packages/stitch-client/src/stitch/client/async_client.py:57))
   and would carry the batch tag — so without the exemption EL would conclude at
   startup that the API is down.
2. *Never count them as interactive activity.* Subtler and worse. If the every-5s
   healthcheck bumped `last_finished_at`, any `quiet_ms > 5000` would
   **permanently starve batch traffic with zero human load** — a value that looks
   conservative would silently mean "never run." Skipping the accounting makes
   that class of misconfiguration impossible.

**Middleware order.** Registered in `register_middlewares`
([middleware.py:23](deployments/api/src/stitch/api/middleware.py:23)) *before*
`RequestTimingMiddleware`, so the timing middleware stays outermost and the
deferral **is** included in the logged `duration_ms`. Hiding the wait would make
the gate invisible in exactly the tooling used to verify it. The gate logs its
own wait separately (its own logger, so this commit stays self-contained and does
not touch `RequestTimingMiddleware`'s fields).

**Settings** — alongside `slow_query_ms` / `log_all_queries`, the same shape of
operational knob, resolved from bare env vars as that file does:

Two knobs, not three — the poll interval is a module constant (see above):

| Field | Default | Env | Meaning |
|---|---|---|---|
| `batch_yield_enabled` | `False` | `BATCH_YIELD_ENABLED` | master switch |
| `batch_yield_quiet_ms` | `1500.0` | `BATCH_YIELD_QUIET_MS` | how long humans must be silent before batch resumes |
| `batch_yield_max_wait_ms` | `5000.0` | `BATCH_YIELD_MAX_WAIT_MS` | hard cap on any one deferral |

`max_wait_ms` gets an upper bound (`le=20000.0`) at the settings layer: it is the
one value where a fat-fingered number produces a confusing *client-side* timeout
in a different service, so it is worth catching at startup rather than in prod
logs. Defaults of 1500/5000 are deliberately modest — see the starvation
tradeoff under Risks.

Default off satisfies the prod-safe requirement; the `api` service already reads
`.env` via `env_file` ([docker-compose.yml:12](docker-compose.yml:12)), so
enabling it in dev needs no compose change — just `.env` plus a documented entry
in `env.example`.

**Tests** — new `deployments/api/tests/test_admission.py`, following the
`ASGITransport`/`AsyncClient` pattern already in
[test_middleware.py:13](deployments/api/tests/test_middleware.py:13). Inject the
clock and sleep as constructor parameters (defaulting to `time.monotonic` /
`asyncio.sleep`) so the quiet-window behavior is tested deterministically with a
fake clock and a recording sleep, with no wall-clock waits. Cases: untagged
request is never delayed; `batch` on an idle server is never delayed; `batch`
within the quiet window waits; `batch` waits while an interactive request is in
flight; wait is bounded by `max_wait_ms` and then proceeds; the in-flight counter
returns to zero after a handler raises; health and `OPTIONS` are exempt; gate
disabled is a total no-op.

## Commit 2 — EL: declare itself as batch traffic

**Mandatory — the gate is completely inert without it.** Commit 1 ships a
middleware that nothing triggers until some caller tags itself.

EL declares itself `batch` via the existing `headers_provider` seam
([async_client.py:22](packages/stitch-client/src/stitch/client/async_client.py:22),
called per request at
[async_client.py:266](packages/stitch-client/src/stitch/client/async_client.py:266)) —
a small wrapper composed over `env_bearer_token_headers_provider()` in
[client.py:33](deployments/entity-linkage/src/stitch/entity_linkage/client.py:33).
No change to `AsyncStitchClient`'s interface is needed, and the client package
stays generic — it does not hardcode a traffic class, because seed/ETL/LLM use the
same client and should classify themselves independently.

`validate_downstream_auth_config_at_startup`
([client.py:19](deployments/entity-linkage/src/stitch/entity_linkage/client.py:19))
stays on the bare provider; it only validates that the token env var is set.

No EL setting for this: EL *is* batch traffic, so it always tags itself. Per
"favor sensible defaults over requiring configuration," there is nothing to
configure — and the header is inert unless the API's gate is enabled.

**Test** — extend
`deployments/entity-linkage/tests/test_client.py`, which already exercises
`env_bearer_token_headers_provider`: assert the composed provider returns both
`Authorization` and the traffic-class header, so a refactor cannot silently drop
the tag and quietly un-throttle EL.

**No 429 handling in scope.** The gate defers and then admits; nothing in the
stack emits 429, so there is nothing for the client to tolerate. Recorded as a
follow-up under Out of scope, with the policy sketched there for whenever an
emitter appears.

**One decision to be aware of:** the header name is a wire contract between two
deployables. The API owns it (constant in `admission.py`); EL sets the literal in
its own `client.py` with a comment cross-referencing it. The API does not depend
on the client package and EL does not depend on the API package, so a shared
constant would mean a new dependency edge for one string — not worth it. The
drift risk is real but small and is covered by the end-to-end check in
Verification step 3, which fails visibly if the names disagree (EL would simply
never be throttled).

## Commit 3 — Deployment: unpin the entity-linkage container resources

`.github/workflows/build-and-deploy.yml` — remove `cpu: "2.0"` / `memory:
"4.0Gi"` from `deploy-entity-linkage` so it takes the platform default, as the
API does.

Two things to know before doing this:

- **Container Apps couples cpu and memory** in fixed ratios, so both come out
  together; there is no memory-only unpin. (The "4x" is CPU: 2.0 vs the ~0.5
  default.)
- **This will not shrink the existing container apps.** The "Reassert resources
  and replica scaling" step only passes `--cpu`/`--memory` when those inputs are
  non-empty
  ([deploy-container.yml:228](.github/workflows/deploy-container.yml:228)), so
  blanking them means the workflow stops asserting the value — it does not reset
  it. Already-deployed EL apps keep 2.0/4.0Gi until someone explicitly resizes
  them. That is a write against Azure, so it is listed under Verification for
  you to run, not something this plan performs.

Expectation to set honestly: this is a **provisioning cleanup, not a throttle.**
EL is I/O-bound on sequential API calls, so giving it less CPU will not
materially reduce its request rate. The gate in Commit 1 is what changes EL's
duty cycle.

## Commit 4 — API: memoize token claims + declare DB pool limits

Two small, related reductions in per-request cost. Could be split further if
review prefers.

- **Memoize validated claims** by token in
  [auth.py:99](deployments/api/src/stitch/api/auth.py:99), bounded and
  respecting token `exp`. EL reuses one static bearer token
  ([auth.py:9](packages/stitch-client/src/stitch/client/auth.py:9)) for an entire
  run, so this removes an RSA verify from every EL request — and helps
  interactive traffic equally, since a browser session reuses its token too.
- **Declare pool limits explicitly** in
  [db/config.py:53](deployments/api/src/stitch/api/db/config.py:53), which today
  sets no `pool_size`/`max_overflow`/`pool_timeout` and so silently runs on
  SQLAlchemy defaults (5 + 10 overflow, 30s timeout). Making the real ceiling
  visible is the point.

Worth flagging while here: pool exhaustion raises `TimeoutError`, which the
`OperationalError` → 503 handler
([main.py:53](deployments/api/src/stitch/api/main.py:53)) does **not** catch, so
it surfaces to clients as a 500.

---

## Risks to set expectations about

1. **Steady interactive traffic can starve batch traffic.** If a human keeps the
   API busier than `quiet_ms`, every EL request pays the full `max_wait`: at 5s
   that is ~12 requests/min, so a 10k-resource pass at ~3 requests each becomes
   tens of hours instead of minutes. `max_wait_ms` guarantees forward progress but
   not throughput. Keep `quiet_ms` modest; do not raise it casually.
   **Good news, verified:** the frontend's 2s status poller targets
   `config.entityLinkageBaseUrl` — the entity-linkage service on :8001, **not** the
   API ([EntityLinkagePage.jsx:209](deployments/stitch-frontend/src/pages/EntityLinkagePage.jsx:209)) —
   so simply watching the linkage page will not hold the API's quiet window open.
2. **The gate cannot preempt.** An interactive request arriving 1ms after a batch
   request was admitted still queues behind a full expensive query. This improves
   the *average* by keeping EL idle while humans are active; it does not fix a
   single collision. Worth saying out loud, or the first slow page load gets
   reported as the feature not working.
3. **Deferred requests inflate `duration_ms` and span duration.** The gate sits
   inside `RequestTimingMiddleware` (deliberately — hiding the wait would make it
   invisible in the very tooling used to verify it), and OTel wraps the whole
   stack. Anyone reading a perf capture without knowing about `gate_wait_ms` will
   see a phantom regression on `GET /oil-gas-fields/`. Mitigated by the gate's own
   correlated log line and a note in PERFORMANCE.md.
4. **Per-worker state.** The counter lives in one middleware instance in one
   process — correct for the single-worker deployment
   ([Dockerfile:47](deployments/api/Dockerfile:47)), and silently a partial view
   under `--workers N`, where each worker sees only its own share of interactive
   traffic and releases batch traffic too eagerly. Worth a comment mirroring the
   existing limitations note at
   [jobs.py:8](deployments/entity-linkage/src/stitch/entity_linkage/jobs.py:8).
5. **Path-based exemption assumes no prefix-stripping proxy.** Compose maps ports
   directly and uvicorn runs with no `--root-path`, so `scope["path"]` is
   `/api/v1/health` today. Worth a comment next to the constant.

## Out of scope — surfaced, not fixed

- **The root cause of EL's volume.** `link_all` is `O(resources × pages)`
  against the most expensive endpoint in the system. A bulk or normalized-name
  match endpoint would cut EL's API load by orders of magnitude, and
  [matching.py:11](deployments/entity-linkage/src/stitch/entity_linkage/matching.py:11)
  already records it as a tracked follow-up (STIT-573). This is the real fix;
  the gate makes the dev server usable in the meantime.
- `matching.py:75` calls `iter_oil_gas_fields(q=seed_name)` without
  `page_size`, so the inner search silently inherits the client default of 50
  rather than the caller's 200 — more round-trips than intended.
- `echo=not settings.is_prod` in
  [db/config.py:55](deployments/api/src/stitch/api/db/config.py:55) logs every
  statement in dev, a cost EL's firehose multiplies.
- The API cannot distinguish machine from human callers: `TokenClaims` does not
  read `gty`/`azp`, and `get_current_user` JIT-provisions a `users` row for any
  `sub`. The in-flight `feat/add-m2m-to-client` branch would give each service a
  distinct `<client_id>@clients` sub — a durable signal the traffic-class header
  can later be keyed off instead, without changing the gate itself.
- The API pins no `cpu`/`memory` and so runs on ~0.5 vCPU.
- **The client treats every non-2xx as fatal.** `_raise_for_status`
  ([async_client.py:329](packages/stitch-client/src/stitch/client/async_client.py:329))
  raises on any error status and `matching.py` tolerates only 400
  ([matching.py:37](deployments/entity-linkage/src/stitch/entity_linkage/matching.py:37)),
  so a 429 from *any* future source — an Azure ingress throttle, a proxy or WAF, or
  the gate if it is ever switched to shed — would kill a multi-hour linkage run.
  Deliberately not fixed now: nothing emits 429 today. When something does, the
  policy is honor `Retry-After` **clamped to ≤30s** (never trust the header
  outright), otherwise 1s/2s/4s with jitter, and bound the whole thing with a
  **deadline computed once on entry** — not an attempt count, because the client's
  `timeout=30.0` is per *attempt*, so 4 naive attempts allow ~2 minutes per logical
  call. Retrying POSTs is safe: 429 means rejected-not-processed, and
  `create_merge_candidate` is already deduped server-side by fingerprint.

## Verification

Ordered so each commit is checked on its own.

1. **Unit/integration tests** — `make test`, then `make check` for lint, format,
   and lockfile.
2. **Gate behavior, deterministic** — tests drive the quiet-window logic
   directly rather than sleeping on wall-clock.
3. **End-to-end, the actual success criterion.** Bring up the stack
   (`make dev-docker`), then use the tooling this repo already has instead of
   eyeballing it:
   - Baseline: drive interactive load and record route latency via
     `tools/analyze_logs.py`, per [PERFORMANCE.md](deployments/PERFORMANCE.md).
   - Start a linkage run, drive the same interactive load tagged with a
     different `X-Stitch-Perf-Scenario` label, and compare with
     `--group-by scenario`. This is precisely what that flag was built for.
   - Confirm the run completes: `GET /api/v1/link/status` ends `succeeded`, not
     `failed`.
   - Repeat with the gate disabled to confirm the delta is the gate.
4. **Prod-safety check** — with the flag unset, confirm the gate is inert and
   request handling is byte-for-byte unchanged.
5. **Azure resize (yours to run, not mine).** Commit 3 does not shrink existing
   apps. Resizing is a write against Azure, so the exact `az containerapp
   update` command will be provided for you to review and run.
