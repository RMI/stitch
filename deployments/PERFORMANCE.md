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
| `API_LOG_LEVEL` | `info` | events log at INFO; this already shows them |

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

> ⚠️ `LOG_LEVEL` is **not** read from `.env` for the compose `api` service — the
> `environment:` block hard-sets it from `API_LOG_LEVEL`. Use `API_LOG_LEVEL` to
> change the level. `LOG_ALL_QUERIES` / `SLOW_QUERY_MS` pass through `.env` fine.

### Deployed (Azure Container Apps)

Leave `LOG_ALL_QUERIES=false` and set `SLOW_QUERY_MS` per lane (200 is a sane
start — only genuinely slow queries are recorded, keeping log volume sane).

---

## Step 2 — Drive traffic

Make sure the DB has realistic row counts first. The `full` profile (used by
`make reboot-docker` and `make dev-docker`) includes the `seed` service, so a
fresh stack is already seeded; tune volume with `FAKER_POST_COUNT` in `.env`
(see [`deployments/seed`](seed)). To re-seed an existing stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml \
  --profile seed up seed --build
```

Then generate load against the endpoint you suspect. Dev lanes run with auth
disabled, so plain `curl` works. A simple repeat loop is enough to surface a hot
query:

```bash
# hammer the list endpoint 200x
for i in $(seq 200); do
  curl -s -o /dev/null "http://localhost:8000/api/v1/oil-gas-fields/?page=1&page_size=50"
done
```

For concurrency/throughput numbers, use a load tool if you have one installed
(`hey`, `wrk`, `ab`):

```bash
hey -n 500 -c 20 "http://localhost:8000/api/v1/oil-gas-fields/?page=1&page_size=50"
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
request, for hunting N+1), `--queries-only`, `--routes-only`.

Example output:

```
QUERIES — top 3 by total
  count    total_ms     mean      p95      max  share                     statement
    120     36276.2    302.3    405.4    418.2  ████████████████████████  SELECT r.id, max(case when p.priority=? ...
    120       641.4      5.3      8.7      8.9  ························  SELECT count(*) FROM resources
    300       348.3      1.2      1.9      2.0  ························  SELECT * FROM oil_gas_field_sources WHERE pk = ?

ROUTES — top 3 by total
  reqs  mean_ms   p95_ms   max_ms  avg_q  max_q  errs  route
   125    396.3    489.9   1433.8    3.0      3     5  /api/v1/oil-gas-fields/
    60    103.6    156.9    159.4   14.9     18     0  /api/v1/oil-gas-fields/{id}  ⚠ N+1?
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
- **`errs`** counts 5xx responses per route.

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
