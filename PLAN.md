# Azure performance dashboarding + per-PR load testing

## Context

We want to compare API performance **across PRs** (and watch it evolve within a
PR across successive Actions runs) on our real Azure cloud environment — the
cloud equivalent of the local Grafana/Prometheus stack that was prototyped in
the now-closed [PR #147](https://github.com/RMI/stitch/pull/147) (closed only
because its base branch was superseded, not because the approach was rejected).

Today the repo already has the pieces to build on:
- **Per-PR deploys exist**: every PR gets `pr-{N}-api` (+ its own DB) in the
  `development` lane, with `DEPLOYMENT_NAME=pr-{N}`, `DEPLOYMENT_LANE`,
  `ENVIRONMENT` already set as env vars on the API
  (`.github/workflows/build-and-deploy.yml:293`).
- **Traces-only OTel** flows to a per-lane `{lane}-otel-collector` Container App
  → `azuremonitor` exporter → **Application Insights**
  (`deployments/otel-collector/config-azure.yaml`,
  `packages/stitch-observability/src/stitch/observability/tracing.py`).
- **No metrics pipeline, no Prometheus, no Grafana** — this is the gap.
- `X-Perf-Scenario` is already recorded as span attr `stitch.scenario` and on the
  structured request/query logs
  (`deployments/api/src/stitch/api/observability/request_logging.py`) — a ready
  segmentation seam.
- `run-seed.yml` runs the seed container against a deployed lane — the template
  for a load-gen job.
- `deployments/PERFORMANCE.md` already documents the enable→drive→analyze loop
  and names the Azure Monitor OTel distro as the intended next step.

**Outcome:** an Azure-managed Grafana dashboard that overlays flat-out k6
load-test results per PR / per Actions run, backed by managed Prometheus, with
click-through to App Insights traces for root-cause — plus a per-PR CI load test
and both the load-gen and seed jobs unified onto Azure Container Apps Jobs.

## Locked decisions

1. **Metrics store:** Azure Monitor Workspace (managed Prometheus) for load-test
   metrics; App Insights stays for trace drill-down; **Azure Managed Grafana**
   holds both datasources.
2. **Trigger:** load test runs on **every PR** automatically (with warm-up +
   per-run tagging; see Risks for shared-infra mitigations).
3. **Job mechanism:** k6 runs via `docker run grafana/k6` **in the GitHub
   runner**, exactly like `run-seed.yml` today (runners are Azure-hosted, and the
   real comparison signal is server-side, so in-network origin buys little).
   **Seed is NOT migrated** — instead seed and load-test are unified into one
   flag-controlled workflow: seed stays its own in-runner docker step, optionally
   chained before the load test.
4. **Provisioning:** the shared, long-lived resources (Grafana, Monitor
   Workspace, DCE/DCR, role assignments) are **provisioned by hand once** and
   **documented**; only the **dashboards are committed as code**.

## Architecture

```
              per-PR CI (build-and-deploy.yml)
                        │
      ┌─────────────────┴───────────────┐
      ▼                                  ▼
 deploy pr-N-api          run-perf.yml (GitHub runner, docker)
      │                     ├─ [if run-seed]     docker run seed  ─► pr-N-api
      │ spans (OTLP)        └─ [if run-loadtest]  docker run k6    ─► pr-N-api
      ▼                            │  labels: pr, run_id, sha
 {lane}-otel-collector             │  remote-write (Entra token from runner az login)
      │  ── azuremonitor ──►        ▼
      │        App Insights   Azure Monitor Workspace
      │  (+ optional spanmetrics →  (managed Prometheus)
      ▼         workspace)               ▲
  App Insights  ◄──── KQL ──── Azure Managed Grafana ──► k6-pr-compare
  (trace drill-down)            (both datasources)       api-live-red
```

## Work items

### A. One-time cloud setup — by hand, documented (no IaC)

Document every step in a new `deployments/OBSERVABILITY_SETUP.md` (portal / `az`
commands, resource names, role assignments) so it is reproducible.

1. **Azure Monitor Workspace** (managed Prometheus) in the same region/RG as the
   Container Apps environment.
2. **Data Collection Endpoint (DCE) + Data Collection Rule (DCR)** targeting the
   workspace. This is the real complexity of managed Prometheus: standalone
   remote-write (non-AKS) ingests via the DCE endpoint
   `…/dataCollectionRules/<dcr-immutable-id>/…/api/v1/write` with an **Entra
   bearer token** (resource `https://monitor.azure.com`). Capture the ingestion
   URL + stream name for the k6 job.
   - *Fallback if remote-write proves fiddly:* a lightweight self-hosted
     `prom/prometheus` Container App with `--web.enable-remote-write-receiver`
     (as in #147) added as a Grafana datasource. Note this in the doc; prefer
     the managed workspace.
3. **Azure Managed Grafana** instance. Add two datasources: the Monitor
   Workspace (Prometheus/PromQL) and Azure Monitor (App Insights/Log Analytics,
   KQL). Give the load-test author(s) Grafana Editor/Admin.
4. **Identity + roles:** grant the **CI OIDC service principal**
   (`AZURE_CLIENT_ID`) **Monitoring Metrics Publisher** on the DCR/workspace, so
   the runner's existing `az login` can mint a usable ingestion token for k6's
   remote-write; grant Grafana's identity **Monitoring Reader** on the workspace.
5. Record the Grafana URL and workspace query endpoint as GitHub Actions **vars**
   (e.g. `GRAFANA_URL`, `AZURE_MONITOR_WORKSPACE_*`, `LOADTEST_DCE_INGEST_URL`,
   `LOADTEST_DCR_STREAM`) for the CI job and PR-comment deep-links.

### B. Repo infrastructure

- **`deployments/loadtest/`** (port from #147 diff, saved at
  `…/scratchpad/pr147.diff`):
  - `script.js` — reuse the constant-arrival-rate read-mix k6 scenario almost
    verbatim. Change the `testid=<git-sha>` tagging to **three labels**:
    `pr`, `run_id`, `sha` (read from `__ENV`), so dashboards can segment by PR
    *and* watch evolution across runs within a PR. Keep the `kind` per-endpoint
    tags and the `http_req_failed: rate<0.05` threshold.
  - `Dockerfile` — thin image over `grafana/k6` that COPYs `script.js`; entrypoint
    wraps `k6 run` (avoid the #147 `k6 k6 run` double-entrypoint bug). Built &
    pushed to ghcr like the seed/otel images.
  - `README.md` — how to run locally and on-demand.
- **`deployments/loadtest/grafana/dashboards/`** (committed as code, decision 4):
  - `k6-pr-compare.json` and `api-live-red.json` — port from #147; repoint the
    datasource to the Managed Grafana Prometheus datasource UID; convert the
    `$testid` template var to `$pr` + `$run_id` (multi-select from
    `label_values(...)`). Import into Managed Grafana by hand (documented).
- **`deployments/otel-collector/config-azure.yaml`** (optional, enables the
  `api-live-red` server-side RED dashboard): add the `spanmetrics` connector
  (buckets/dimensions from #147) and a `prometheusremotewrite` exporter →
  Monitor Workspace (Entra auth via the collector's managed identity). If
  deferred, ship only the k6-pr-compare dashboard first.

### C. CI — unified seed+load-test workflow (in GitHub runner)

- **New reusable workflow `.github/workflows/run-perf.yml`** that supersedes the
  standalone `run-seed.yml` (model closely on `run-seed.yml` — same GHCR
  login / `docker run` / comment-JSON shape):
  - Inputs: `deployment-lane`, `seed-image-name`, `loadtest-image-name`,
    `api-url`, `run-seed` (bool), `run-loadtest` (bool); workspace ingest
    URL/stream from Actions vars. Secret: `stitch-client-bearer-token`
    (reuse `STITCH_CLIENT_PRIVILEGED_BEARER_TOKEN`).
  - **Seed step** (`if: run-seed`): identical to today's `run-seed.yml` body —
    `docker run` the seed image with the current env
    (`FAKER_POST_COUNT`/`RANDOM_SEED`/`SEED_SOURCE`/`NULL_PROBABILITY`,
    `-v .../seed/data:/mnt/data:ro`). Unchanged behavior.
  - **Load-test step** (`if: run-loadtest`): `az login` is already available for
    OIDC; mint a **short-lived Entra token**
    (`az account get-access-token --resource https://monitor.azure.com`) into
    `K6_PROMETHEUS_RW_BEARER_TOKEN`, then `docker run grafana/k6` (our thin image)
    with env: `BASE_URL`, `BEARER_TOKEN`, `K6_VUS/K6_RATE/K6_DURATION` (~1–2 min),
    `K6_OUT=experimental-prometheus-rw`, `K6_PROMETHEUS_RW_SERVER_URL`,
    `K6_PROMETHEUS_RW_TREND_STATS=p(90),p(95),p(99),avg,min,max,med`, and label
    envs `LOADTEST_PR`, `LOADTEST_RUN_ID` (`${{ github.run_id }}`), `LOADTEST_SHA`.
  - **Warm-up** before the load test (dev apps scale to zero): curl
    `/api/v1/health` and one real `oil-gas-fields` request until 200 so cold-start
    latency doesn't pollute the first samples.
  - Emit `comment-json-perf.json` with a **Grafana deep-link** pre-filtered to
    this `pr`+`run_id` (the existing `comment-pr-summary.yml` renders it).
- **Wire into `.github/workflows/build-and-deploy.yml`:** add a `build-loadtest-…`
  image job to the fan-out; replace the `run-seed` job (`:461`) with a `run-perf`
  job `needs: [deploy-api, deploy-db, build-seed-…, build-loadtest-…]`, passing
  `run-seed: ${{ needs.deploy-db.outputs.database-created }}` and
  `run-loadtest: true`, gated to the `development` lane. Update `comment-summary`
  `needs` (`:501`) from `run-seed` to `run-perf`.

### D. Seed — unchanged, just re-orchestrated

No seed image or logic change. `run-seed.yml` is folded into `run-perf.yml`'s
seed step (the standalone file can be deleted once `run-perf.yml` covers its one
caller, or kept as a thin shim). Seed continues to run only on a freshly-created
`pr-{N}` DB via the `run-seed` flag. Verify a fresh PR DB is still seeded
identically.

### E. Docs — update `deployments/PERFORMANCE.md`

Add a **"Cloud dashboards (Grafana) & per-PR load testing"** section covering:
- What the load test does, when it runs (every PR), and the label scheme
  (`pr`/`run_id`/`sha`).
- The Grafana URL and how to **compare PRs** (select `$pr` values) and **watch
  evolution within a PR** (select `$run_id` values).
- How to read the panels (reuse the existing "how to read it" prose) and the
  **drill-down**: spot a p95 regression in Prometheus → pivot to the App Insights
  trace/slow-query for the same route/time window.
- How to run the load test **on-demand** and point it at any lane.
- Note the App Insights vs Prometheus split (aggregate comparison vs per-request
  root-cause) so future maintainers know which tool answers which question.
- Update the "Future / OpenTelemetry" note to reflect that metrics/dashboards now
  exist.

## Critical files

- `.github/workflows/run-seed.yml` — template for `run-perf.yml` (GHCR login,
  `docker run`, comment-JSON) and the seed step it absorbs.
- `.github/workflows/deploy-container.yml` — `az login`/OIDC patterns to reuse
  for minting the Monitor token.
- `.github/workflows/build-and-deploy.yml:461` (run-seed job), `:501` (comment
  `needs`) — where to swap in `run-perf`.
- `.github/workflows/resolve-deployment-context.yml` — source of `pr-{N}`.
- `deployments/otel-collector/config-azure.yaml` — optional spanmetrics.
- `deployments/PERFORMANCE.md` — docs update.
- `deployments/loadtest/**` (new), `deployments/OBSERVABILITY_SETUP.md` (new).
- Reference for reuse: `…/scratchpad/pr147.diff` (k6 script, dashboards, Makefile
  targets, spanmetrics/prometheus configs).

## Risks & mitigations

- **Shared dev infra (every-PR choice):** the `development` lane shares one
  Postgres server and one collector across all `pr-{N}` deploys, and dev apps
  scale to zero. Mitigate with the warm-up step and per-run tagging; accept that
  simultaneous PR load tests can contend (surface run metadata so contended runs
  are identifiable). Revisit an opt-in label if contention/cost bites.
- **Managed Prometheus remote-write auth:** DCE/DCR + Entra token is the fiddly
  part; documented in setup, with the self-hosted-Prometheus fallback if needed.
  The runner mints the token from its existing OIDC `az login` (no new identity).
- **Seed re-orchestration:** logic is unchanged, but confirm a fresh `pr-{N}` DB
  is still seeded identically after folding `run-seed.yml` into `run-perf.yml`
  before deleting the standalone file.
- **Cost:** managed Prometheus bills per sample; a 1–2 min flat-out test per PR is
  modest but non-zero — note retention settings in the setup doc.

## Verification

1. **Local k6 first:** run `deployments/loadtest/script.js` against a local
   `make reboot-docker` stack to confirm the scenario + tags work before cloud.
2. **One PR end-to-end:** open a draft PR; confirm the CD pipeline deploys
   `pr-{N}-api`, `run-perf` seeds the fresh DB, then the k6 step runs ~1–2 min
   and exits 0.
3. **Grafana:** open the deep-link from the PR comment; confirm k6 series appear
   labeled with this `pr`/`run_id`/`sha`, and that selecting a second PR overlays
   both. Confirm App Insights datasource resolves a matching trace.
4. **Evolution:** push a second commit to the same PR; confirm a new `run_id`
   series appears alongside the first under the same `pr`.
5. **Drill-down:** from a Prometheus latency spike, pivot to the App Insights
   trace for the same route/window and land on the expected slow query.
6. Confirm the `run-perf` job's seed and load-test steps both succeeded in the
   Actions logs, and re-running the pipeline on the same PR (DB already present)
   skips seed (`run-seed=false`) and runs load-test only.
