# Load testing (k6), seeding & PR-comparison dashboards

A flat-out [k6](https://k6.io) load test of the stitch API's read-heavy
`oil-gas-fields` endpoints, plus a k6-based **seeder** that replaces the old
Python `stitch-seed` service. It runs on **every PR** against that PR's freshly
deployed cloud instance, streams results to Azure Monitor managed Prometheus,
and renders them in Azure Managed Grafana so you can compare response times
**across PRs** and **across runs within a PR** — reads *and* writes.

For the wider perf story (server-side query profiling, drill-down into slow
queries) see [`../PERFORMANCE.md`](../PERFORMANCE.md). For the one-time cloud
setup (Grafana, Monitor Workspace, remote-write auth) see
[`../OBSERVABILITY_SETUP.md`](../OBSERVABILITY_SETUP.md).

## What's here

| Path | Purpose |
|---|---|
| `script.js` | The load-test scenario: weighted read-mix (list/search 55%, detail 30%, filter-options 15%), `constant-arrival-rate` executor. k6 built-ins only — no bundling. |
| `seed.js` | The seeder: POSTs the committed demo data + `SEED_VOLUME` faker-generated fields. Imports `@faker-js/faker`, so it is **bundled** with esbuild in the Docker build. |
| `data/*.json` | Committed demo payloads (merge / llm / source-value demos), bundled into `seed.js`. |
| `Dockerfile` | Multi-stage: a Node/esbuild stage bundles `seed.js`; the k6 stage ships `script.js` + `seed.dist.js`. Built & pushed per-PR by the CD pipeline. |
| `package.json` | faker + esbuild for the bundle step. |
| `prometheus.yml`, `grafana/` | The **local** Prometheus config + Grafana datasource/dashboard provisioning (see local stack below). |
| `grafana/dashboards/k6-pr-compare.json` | Grafana dashboard: read + write latency (avg/p95/p99) per endpoint, per run, with `$pr`/`$run` filters. **The PR-comparison view.** |
| `grafana/dashboards/api-live-red.json` | Grafana dashboard: server-side RED (rate/errors/duration) per PR, from **Application Insights** via the Azure Monitor datasource (KQL). **Azure-only** — App Insights doesn't exist locally. |

## How it runs in CI

The reusable `run-perf.yml` workflow (called from `build-and-deploy.yml`) runs
this image twice against the deployed PR instance — `seed.dist.js` then
`script.js` — each with `--out experimental-prometheus-rw` to the managed
Prometheus endpoint, tagging every run:

```
--tag pr=<PR number>  --tag run_id=<gh run id>  --tag sha=<short sha>
--tag run=pr<PR>-<run_id>      # self-labeling composite; the dashboard's x-axis
```

`run` uniquely identifies one Actions run, so selecting several PRs compares
them, and selecting one PR's runs shows how it evolved commit-to-commit. Seed
POSTs are tagged `name=create`, so create latency shows in the dashboard's
write-path panels alongside the read results.

## Local stack

Bring up the full observability + dashboard stack, then run the load test:

```bash
make reboot-docker-heavy   # api + friends + seed + collector/jaeger + prometheus + grafana
make loadtest              # runs script.js once; metrics -> local Prometheus -> Grafana
```

- Grafana: <http://localhost:3001> (anonymous view). **`k6-pr-compare`** is
  auto-provisioned and works locally — it selects its Prometheus source via a
  `datasource` template variable, so the same JSON renders here and in Azure with
  no edits. **`api-live-red` is Azure-only** (it queries Application Insights,
  which has no local equivalent).
- Prometheus: <http://localhost:9090> · Jaeger: <http://localhost:16686>
- For local span-derived RED, enable OTEL export in `.env` (`OTEL_ENABLED=true`,
  `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`) — the collector then
  emits `spanmetrics_*` to the local Prometheus, which you can explore in Grafana
  **Explore** (there's no committed local RED dashboard; `api-live-red` is the
  Azure/App-Insights one).
- Seed volume is `SEED_VOLUME` in `.env` (default 50 locally). Bump it before a
  meaningful load test so the query-expensive paths have real data.

### Ad-hoc run against any target

The image ENTRYPOINT is `k6 run`; pass a script path + flags:

```bash
IMG=$(docker build -q -f deployments/loadtest/Dockerfile .)
docker run --rm --network host \
  -e BASE_URL=http://localhost:8000 -e K6_DURATION=30s \
  "$IMG" /scripts/script.js --tag run=local-$(git rev-parse --short HEAD)
# or seed:  "$IMG" /scripts/seed.dist.js   (with -e BEARER_TOKEN=… -e SEED_VOLUME=…)
```

> **Auth:** protected endpoints 401 before touching the DB, so an unauthenticated
> run measures nothing. Locally `AUTH_DISABLED=true` is the default; against a
> deployed lane pass `-e BEARER_TOKEN=<token>`. See the auth note in
> [`../PERFORMANCE.md`](../PERFORMANCE.md).
