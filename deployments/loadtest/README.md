# Load testing (k6) & PR-comparison dashboards

A flat-out [k6](https://k6.io) load test of the stitch API's read-heavy
`oil-gas-fields` endpoints. It runs on **every PR** against that PR's freshly
deployed cloud instance, streams results to Azure Monitor managed Prometheus,
and renders them in Azure Managed Grafana so you can compare response times
**across PRs** and **across runs within a single PR**.

For the wider perf story (server-side query profiling, drill-down into slow
queries) see [`../PERFORMANCE.md`](../PERFORMANCE.md). For the one-time cloud
setup (Grafana, Monitor Workspace, remote-write auth) see
[`../OBSERVABILITY_SETUP.md`](../OBSERVABILITY_SETUP.md).

## What's here

| Path | Purpose |
|---|---|
| `script.js` | The k6 scenario: weighted read-mix (list/search 55%, detail 30%, filter-options 15%) with randomized params, `constant-arrival-rate` executor. |
| `Dockerfile` | Thin image over `grafana/k6` with `script.js` baked in. Built & pushed per-PR by the CD pipeline. |
| `grafana/dashboards/k6-pr-compare.json` | Grafana dashboard: avg/p95/p99 per endpoint, per-run, with `$pr`/`$run` filters. **The PR-comparison view.** |
| `grafana/dashboards/api-live-red.json` | Grafana dashboard: live server-side RED (rate/errors/duration) from span-derived metrics. Needs the optional collector `spanmetrics` pipeline (see setup doc). |

## How it runs in CI

The reusable `run-perf.yml` workflow (called from `build-and-deploy.yml`) runs
the k6 image with `--out experimental-prometheus-rw` pointed at the managed
Prometheus remote-write endpoint, tagging each run:

```
--tag pr=<PR number>  --tag run_id=<gh run id>  --tag sha=<short sha>
--tag run=pr<PR>-<run_id>      # self-labeling composite; the dashboard's x-axis
```

`run` uniquely identifies one Actions run, so selecting several PRs compares
them, and selecting one PR's runs shows how it evolved commit-to-commit.

## Running locally

Against a local stack (`make reboot-docker`, API on `:8000`). k6 tunables are
env vars; the target is `BASE_URL`.

```bash
# Local default auth is disabled, so no token is needed. Point at the host API:
docker run --rm --network host \
  -e BASE_URL=http://localhost:8000 \
  -e K6_VUS=20 -e K6_RATE=50 -e K6_DURATION=1m \
  $(docker build -q -f deployments/loadtest/Dockerfile .) \
  --tag run=local-$(git rev-parse --short HEAD)
```

To stream to a local Prometheus (e.g. the docker-compose stack from the setup
doc's fallback), add `-e K6_OUT=experimental-prometheus-rw` and
`-e K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write`. Without
`K6_OUT`, k6 just prints its end-of-test summary — handy for a quick check that
the scenario and tags are wired correctly before involving the cloud.

> **Auth:** protected endpoints 401 before touching the DB, so an unauthenticated
> run measures nothing. Locally, `AUTH_DISABLED=true` is the default. Against a
> deployed lane, pass `-e BEARER_TOKEN=<token>` (the CI job uses the privileged
> seed/client token). See the auth note in [`../PERFORMANCE.md`](../PERFORMANCE.md).
