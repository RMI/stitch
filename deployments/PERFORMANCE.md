# Performance testing & query profiling

Stitch's API is instrumented to record **what database queries run, how long
they take, and which endpoint triggered them**. The data is emitted as
structured JSON to stdout — captured by Azure Container Apps → Log Analytics in
the cloud, and readable straight from the terminal locally — so you can find
slow/frequent queries from real data instead of guessing.

This doc covers the basic loop: **enable capture → drive traffic → analyze**.

> The instrumentation lives in the app code
> ([`deployments/api/src/stitch/api/observability/`](api/src/stitch/api/observability/)),
> so it works under any entrypoint that runs the API (`make api-dev`,
> `make reboot-docker`, or the deployed container) — only *how you configure and
> collect it* differs.

---

## What gets captured

Two structured log streams, distinguished by the `logger` field:

| Logger | Emitted | Key fields |
|---|---|---|
| `stitch.api.observability.request` | once per HTTP request (always) | `route`, `method`, `status_code`, `duration_ms`, `db_query_count`, `db_time_ms`, `request_id` |
| `stitch.api.observability.query` | once per query above the slow threshold | `statement` (parameterized SQL, **no bound values**), `duration_ms`, `rowcount`, `route`, `request_id` |

`db_query_count` on a request is the N+1 detector; the `query` stream tells you
*which* statement is expensive.

---

## Step 1 — Enable capture (the knobs)

Configured via env vars (read by [`settings.py`](api/src/stitch/api/settings.py)):

| Env var | Default | Use |
|---|---|---|
| `LOG_ALL_QUERIES` | `false` | `true` logs **every** query — use for local profiling |
| `SLOW_QUERY_MS` | `200` | log only queries at/above this many ms — use in prod |
| `LOG_FORMAT` | `json` | `json` (structured) or `plain` |
| `LOG_LEVEL` | `INFO` | events log at INFO, so the default already shows them |

The request stream is always on. The query stream is gated: by default you only
see queries ≥ 200 ms. For local profiling you usually want **everything**.

### `make api-dev`

Inline:

```bash
LOG_ALL_QUERIES=true make api-dev
```

### `make reboot-docker` (full docker-compose stack)

The `api` service reads `.env`, so add to your `.env`:

```bash
LOG_ALL_QUERIES=true
SLOW_QUERY_MS=0
```

then `make reboot-docker` as usual.

> ⚠️ The settings model reads **`LOG_LEVEL`** (that's the variable to set for
> non-docker runs like `make api-dev`). Under docker-compose, though, the `api`
> service's `environment:` block hard-sets `LOG_LEVEL` from `API_LOG_LEVEL`, so
> for `make reboot-docker` set **`API_LOG_LEVEL`** in `.env` (a plain `LOG_LEVEL`
> there is ignored). `LOG_ALL_QUERIES` / `SLOW_QUERY_MS` pass through `.env` fine
> either way.

### Deployed (Azure Container Apps)

Leave `LOG_ALL_QUERIES=false` and set `SLOW_QUERY_MS` per lane (200 is a sane
start — only genuinely slow queries are recorded, keeping log volume sane).

---

## Step 2 — Drive traffic

Make sure the DB has realistic row counts first. The `full` profile (used by
`make reboot-docker` and `make dev-docker`) includes the `seed` service, so a
fresh stack is already seeded; tune volume by setting `SEED_FAKER_POST_COUNT` in
`.env` (compose maps it to the seed service's `FAKER_POST_COUNT` — a bare
`FAKER_POST_COUNT` in `.env` is ignored; see [`deployments/seed`](seed)). To
re-seed an existing stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml \
  --profile seed up seed --build
```

> **Auth matters here.** Protected endpoints return **401 before the handler
> runs**, so unauthenticated requests do *zero* DB work — you'll see requests
> logged with `db_query_count: 0` and a high `err%`, and no query events. If your
> query report comes back empty or routes show `err%` near 100%, this is almost
> certainly why. Two ways to make load actually hit the DB:
>
> - **Disable auth (simplest, dev only):** set `AUTH_DISABLED=true` in `.env`
>   (allowed when `ENVIRONMENT` is `dev`/`main`/`dev-*`/`pr-*`) and restart the
>   stack — requests then run as a dev user.
> - **Send a token:** reuse the privileged bearer token the `seed` service
>   already authenticates with, read straight from `.env` (see the loop below).

Then generate load against the endpoint you suspect. Pull the token from `.env`
(without printing it), confirm one request is accepted, then hammer the endpoint:

```bash
# Extract the token: everything after the '=', minus quotes / CR.
# (Add a single-quote to the tr set if your value is single-quoted.)
TOKEN=$(sed -n 's/^STITCH_CLIENT_PRIVILEGED_BEARER_TOKEN=//p' .env | tr -d '"\r')

# Sanity check — expect 200, not 401:
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/oil-gas-fields/?page=1&page_size=1"

# Hammer the list endpoint 200x, tagged for comparison:
for i in $(seq 200); do
  curl -s -o /dev/null \
    -H "Authorization: Bearer $TOKEN" \
    -H 'X-Stitch-Perf-Scenario: vol=8k' \
    "http://localhost:8000/api/v1/oil-gas-fields/?page=1&page_size=50"
done
```

> Don't `echo "$TOKEN"` — keep the secret out of your shell history. If the
> sanity check still returns `401`, the running API validates against a
> different token than what's in `.env` (a quick tell is whether the `seed`
> service itself succeeds, since it uses the same one). If auth is disabled
> instead, drop the `Authorization` header — the `TOKEN` line is then unneeded.

For concurrency/throughput numbers, use a load tool if you have one installed
(`hey`, `wrk`, `ab`) — pass the same auth header (and scenario label):

```bash
hey -n 500 -c 20 \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Stitch-Perf-Scenario: vol=8k" \
  "http://localhost:8000/api/v1/oil-gas-fields/?page=1&page_size=50"
```

The instrumentation records every request regardless of how it's generated.

---

## Step 3 — Capture the logs to a file

### Local (`make api-dev`)

```bash
LOG_ALL_QUERIES=true make api-dev 2>&1 \
  | tee /tmp/stitch-raw.log \
  | jq -Rc 'fromjson? | select(.logger | test("observability"))' \
  > /tmp/stitch-events.jsonl
```

### Local (docker-compose)

Run the stack in one terminal; collect `api` logs in another:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml \
  logs --no-log-prefix api > /tmp/stitch-api.log
```

(`--no-log-prefix` keeps lines as pure JSON. The analyzer in the next step also
strips the `api-1 | ` prefix and skips non-JSON lines, so a raw capture is fine.)

This one-shot dump reads whatever the container still has on disk — fine for
modest runs. It does **not** time out, but two things can make earlier events
disappear before you capture them:

- **Container recreation.** `make reboot-docker` (via `clean-docker`) and
  `docker compose down` discard the container's logs entirely. A plain
  stop/start keeps them.
- **Log rotation.** *Only* if the `json-file`/`local` driver has `max-size` /
  `max-file` set (it isn't by default, so logs grow unbounded). If a cap is
  configured, the oldest lines silently roll off once it's hit. Check with:
  `docker compose ... ps -q api` →
  `docker inspect <id> --format '{{json .HostConfig.LogConfig}}'`.

**For large or long runs, capture the live stream instead** — start this
*before* driving load and Ctrl-C when done. `-f` follows; `tee -a` writes to disk
as events arrive, so nothing depends on container retention and it survives a
later `reboot-docker`:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml \
  logs -f --no-log-prefix api | tee -a /tmp/stitch-api.log
```

### Deployed (Log Analytics via `az`)

```bash
az monitor log-analytics query \
  -w <LOG_ANALYTICS_WORKSPACE_ID> \
  --analytics-query '
    ContainerAppConsoleLogs_CL
    | where ContainerName_s == "api"
    | where TimeGenerated > ago(1h)
    | extend p = parse_json(Log_s)
    | where tostring(p.logger) startswith "stitch.api.observability"
    | project line = Log_s' \
  -o tsv > /tmp/prod-events.jsonl
```

---

## Step 4 — Analyze

[`tools/analyze_logs.py`](../tools/analyze_logs.py) (stdlib only — runs with
plain `python3`) ranks queries and routes from any dump:

```bash
python3 tools/analyze_logs.py /tmp/stitch-events.jsonl

# or stream straight from docker
docker compose -f docker-compose.yml -f docker-compose.local.yml \
  logs --no-log-prefix api | python3 tools/analyze_logs.py -
```

Useful flags: `--top N`, `--width N` (statement column),
`--sort {total,count,p95,max,mean,queries}` (`queries` = avg DB queries per
request, for hunting N+1), `--queries-only`, `--routes-only`,
`--group-by scenario` (compare tagged variants — see
[Comparing variants](#comparing-variants-data-volume--params)), `--baseline`.

Example output:

```
QUERIES — top 3 by total
  count    total_ms     mean      p95      max  share                     statement
    120     36276.2    302.3    405.4    418.2  ████████████████████████  SELECT r.id, max(case when p.priority=? ...
    120       641.4      5.3      8.7      8.9  ························  SELECT count(*) FROM resources
    300       348.3      1.2      1.9      2.0  ························  SELECT * FROM oil_gas_field_sources WHERE pk = ?

ROUTES — top 3 by total
  reqs  mean_ms   p95_ms   max_ms  avg_q  max_q   err%  route
   125    396.3    489.9   1433.8    3.0      3   4.0%  /api/v1/oil-gas-fields/
    60    103.6    156.9    159.4   14.9     18   0.0%  /api/v1/oil-gas-fields/{id}  ⚠ N+1?
```

### How to read it

- **`QUERIES` sorted by `total_ms`** = cumulative cost (`mean × count`). The top
  row is the single best optimization target — slow *and* frequent. The `share`
  bar shows how dominant it is.
- **High `count`, low `mean`** = a cheap query run too often (caching / batching
  opportunity) rather than a slow query.
- **`p95` ≫ `mean`** = inconsistent latency (lock contention, cold cache, a bad
  plan for some inputs).
- **`ROUTES` `avg_q` (avg queries/request)** = N+1 smell. A detail endpoint
  firing 15 queries per request is doing per-row lookups; the `⚠ N+1?` flag marks
  ≥ 10. Cross-reference with the query stream to see which statement repeats.
- **`err%`** = share of requests with status ≥ 400 (includes **401/403** auth
  failures, not just 5xx). A route at ~100% `err%` with `avg_q` 0 means the
  requests are being rejected before any DB work — usually unauthenticated load
  (see the auth note in Step 2).

> **Statement truncation.** Query statements are normalized and truncated to a
> fixed prefix (2000 chars) before logging, so queries that differ only past the
> cutoff — large `IN (...)` lists, big CTEs — collapse into a single row in the
> `QUERIES` report. If a row's `count` looks suspiciously high or its statement
> ends in `…`, it may be several distinct queries merged together.

---

## Comparing variants (data volume / params)

To see how the *same* query behaves under different conditions, **tag each batch
of traffic** with an `X-Stitch-Perf-Scenario: <label>` request header. The label is
recorded on every request *and* query event it triggers, so a single log
captures all variants and the analyzer compares them with `--group-by scenario`.
No log slicing, no separate files.

Make sure `LOG_ALL_QUERIES=true` is set in `.env` first (Step 1) so query events
are recorded. Define a shorthand for the compose command:

```bash
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.local.yml"
```

### Variant by data volume (re-seed between runs)

The seed volume is controlled from `.env` via `SEED_FAKER_POST_COUNT` (the
`seed` service reads it; default 5). Re-running the seed service **adds** more
rows, so you can build up a volume ladder on a live stack.

1. **Start the stack at the first volume.** Set `SEED_FAKER_POST_COUNT=1000` in
   `.env`, then bring it up — the `full` profile seeds automatically:

   ```bash
   make reboot-docker        # (foreground; or `$COMPOSE --profile full up -d`)
   ```

2. **Drive load, tagging it with the volume label:**

   ```bash
   for i in $(seq 200); do
     curl -s -o /dev/null -H 'X-Stitch-Perf-Scenario: vol=1k' \
       "http://localhost:8000/api/v1/oil-gas-fields/?page=1&page_size=50"
   done
   ```

3. **Re-seed to a larger volume.** Bump `SEED_FAKER_POST_COUNT` (e.g. to
   `50000`) in `.env`, then re-run *only* the seed service against the running
   stack:

   ```bash
   $COMPOSE --profile seed up seed --build
   ```

4. **Drive load again with a new label:**

   ```bash
   for i in $(seq 200); do
     curl -s -o /dev/null -H 'X-Stitch-Perf-Scenario: vol=50k' \
       "http://localhost:8000/api/v1/oil-gas-fields/?page=1&page_size=50"
   done
   ```

5. **Dump the log once and compare** — both variants are in the same stream:

   ```bash
   $COMPOSE logs --no-log-prefix api > /tmp/perf.log
   python3 tools/analyze_logs.py /tmp/perf.log --group-by scenario
   ```

   ```
   QUERIES by scenario — top 1 (baseline = fastest variant)

   SELECT r.id, max(case when p.priority=? then s.name end) FROM resources r ...
     scenario                   count     mean      p95   total_ms   vs base
     vol=1k                       150     43.9     53.9     6582.0    1.00×  ← base
     vol=50k                      150    394.3    453.7    59147.5    8.99×
   ```

   A statement whose `vs base` ratio climbs steeply with volume is the one that
   scales badly — your culprit. By default the fastest variant is the baseline;
   pin a specific one with `--baseline vol=1k`.

> Re-seeding is **cumulative** (volume keeps growing), which is what you want for
> a volume ladder. For *independent*, repeatable volumes, set
> `SEED_FAKER_POST_COUNT` and run `make reboot-docker` before each labelled run —
> it wipes the DB so the volumes don't stack.

### Variant by query params

Keep the data volume fixed and vary the request between batches, giving each its
own label — the param values are a natural label:

```bash
for ps in 50 500; do
  for i in $(seq 200); do
    curl -s -o /dev/null -H "X-Stitch-Perf-Scenario: page_size=$ps" \
      "http://localhost:8000/api/v1/oil-gas-fields/?page=1&page_size=$ps"
  done
done
$COMPOSE logs --no-log-prefix api > /tmp/perf.log
python3 tools/analyze_logs.py /tmp/perf.log --group-by scenario
```

The `--group-by scenario` view breaks each query/route down by label, so
`page_size=50` and `page_size=500` sit side by side even though they hit the
same route template.

> The `X-Stitch-Perf-Scenario` label is opaque to the server (truncated to 80 chars)
> and recorded only when sent, so it's safe to leave the feature in place — it
> costs nothing on untagged production traffic.

---

## Interpreting → acting

1. Find the top query by `total_ms`.
2. Confirm its plan in Postgres: `EXPLAIN (ANALYZE, BUFFERS) <statement>`.
3. Typical fixes: add/adjust an index, eliminate an N+1 (eager-load with
   `selectinload`), avoid rebuilding an expensive CTE per request, or cache.
4. Re-run the same load and diff the `total_ms` ranking to confirm the win.

The suspected hot path today is the licensed-resource CTE built per request in
[`og_field_resource_actions.py`](api/src/stitch/api/db/og_field_resource_actions.py)
behind `GET /api/v1/oil-gas-fields/`. Let the data confirm it before optimizing.

---

## Notes

- **Query logs are self-limiting in prod** via `SLOW_QUERY_MS`; the per-request
  summary logs on every request (one line each). If that's too chatty at scale,
  raise the threshold or add sampling.
- **No PII in logs** — only parameterized statement text is recorded, never
  bound parameter values.
- **Future / OpenTelemetry**: all emission flows through one seam
  ([`observability/sinks.py`](api/src/stitch/api/observability/sinks.py)). When
  richer analysis is worth it, the Azure Monitor OpenTelemetry distro can emit
  spans (per-query dependency waterfalls, percentiles) from the same timing data
  without reworking the instrumentation. Deliberately not enabled yet.
