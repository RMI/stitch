# Observability setup — Grafana + managed Prometheus (one-time, by hand)

This is the **one-time** cloud setup behind the per-PR load-test dashboards. The
repo commits the dashboards, the k6 image, and the CI job; the shared,
long-lived resources below are provisioned by hand (no IaC in this repo) and
recorded here so the setup is reproducible. Each step has a **Portal** and a
**CLI** track — do whichever you prefer.

You run this once per Azure environment. Day-to-day, the
[`run-perf.yml`](../.github/workflows/run-perf.yml) CI job publishes to what you
provision here, and you read the results in Grafana (see
[`PERFORMANCE.md`](PERFORMANCE.md)). To try the whole thing locally first — same
dashboards, no Azure — see the "Local stack" section in
[`loadtest/README.md`](loadtest/README.md) (`make reboot-docker-heavy` +
`make loadtest`).

## What you're building

```
k6 (GitHub runner) ──remote-write (Entra token)──► Azure Monitor Workspace
  seed.dist.js + script.js                          (managed Prometheus)
                                                          ▲ PromQL
Application Insights ◄── (already exists, traces) ── Azure Managed Grafana
                                                     ├ datasource: Prometheus (auto-linked)
                                                     └ datasource: Azure Monitor (App Insights)
```

Already in place (prereqs — do not recreate): the resource group
(`AZURE_RESOURCE_GROUP`), the Container Apps environment
(`AZURE_CONTAINER_APP_ENVIRONMENT`), Application Insights
(`APPLICATIONINSIGHTS_CONNECTION_STRING`), and the CI OIDC service principal
(`AZURE_CLIENT_ID`). For the CLI track, set:

```bash
RG="<AZURE_RESOURCE_GROUP>"
LOC="<region, e.g. eastus>"
CI_PRINCIPAL="<AZURE_CLIENT_ID>"          # the OIDC app the CD pipeline logs in as
```

---

## 1. Azure Monitor Workspace (managed Prometheus)

**Portal:** Create a resource → search **"Azure Monitor Workspace"** → Create.
Pick the same subscription / resource group / region as the Container Apps
environment; name it `stitch-prometheus`. After it deploys, open it and note its
**Metrics ingestion endpoint** and **Query endpoint** (Overview blade).

**CLI:**
```bash
az monitor account create --name stitch-prometheus -g "$RG" -l "$LOC"
AMW_ID=$(az monitor account show --name stitch-prometheus -g "$RG" --query id -o tsv)
az monitor account show --name stitch-prometheus -g "$RG" \
  --query "{ingest:metrics.prometheusQueryEndpoint, id:id}"
```

## 2. Remote-write ingestion (the fiddly part)

k6 pushes metrics via Prometheus remote-write, authenticated with an **Entra
token** for resource `https://monitor.azure.com` (the CI job mints this with
`az account get-access-token`; no static secret). Remote-write to an Azure
Monitor Workspace goes through a **Data Collection Endpoint (DCE) + Data
Collection Rule (DCR)** — but **you do not create these by hand**: creating the
workspace in Step 1 auto-provisions both (both named `stitch-prometheus`, shown
on the workspace **Overview** as "Data collection endpoint" and "Data collection
rule"). **Do not** use the generic "Create Data Collection Rule" wizard — its
telemetry types (Agent-based / Platform telemetry) are not the Prometheus
remote-write path. Reuse the auto-created pair:

**Portal:**
1. On the workspace **Overview**, note the **Metrics ingestion endpoint**
   (e.g. `https://stitch-prometheus-wxjg.westus2-1.metrics.ingest.monitor.azure.com`).
2. Open the linked **Data collection rule → `stitch-prometheus` → JSON View** and
   copy `properties.immutableId` (format `dcr-…`).
3. On that DCR → **Access control (IAM)** → Add role assignment →
   **Monitoring Metrics Publisher** → assign to the CI service principal
   (`AZURE_CLIENT_ID`). **This needs `Owner` or `User Access Administrator`** on
   the DCR (or its RG/subscription) — if you're a limited admin, hand the CLI
   command below to someone who has it. Assigning at the **resource-group** scope
   instead is fine (covers future DCRs too); DCR scope is tighter.
4. Assemble the remote-write URL (this becomes `LOADTEST_PROMETHEUS_RW_URL` in
   step 4):
   ```
   <metrics-ingestion-endpoint>/dataCollectionRules/<immutableId>/streams/Microsoft-PrometheusMetrics/api/v1/write?api-version=2023-04-24
   ```
   (the `api-version` is version-dependent — confirm against the current docs).

> **Order matters:** don't set `LOADTEST_PROMETHEUS_RW_URL` (step 4) until the
> role assignment above exists. If the URL is set but the principal can't publish,
> k6's remote-write gets 403s and can fail the load-test step. While it's unset,
> the job runs summary-only and never blocks a PR.

**CLI:** (grant the role — requires Owner / User Access Administrator on the scope)
```bash
az role assignment create \
  --assignee "$CI_PRINCIPAL" \
  --assignee-principal-type ServicePrincipal \
  --role "Monitoring Metrics Publisher" \
  --scope "<DCR resource id>"   # DCR -> JSON View -> top-level "id"
```

Capture the ingestion URL — it becomes `LOADTEST_PROMETHEUS_RW_URL` in step 4.

> **Fallback if remote-write proves fiddly** — fully self-contained and
> guaranteed to work with k6 + Grafana. Run a small Prometheus as its own
> Container App:
> ```bash
> az containerapp create -g "$RG" \
>   --environment "$AZURE_CONTAINER_APP_ENVIRONMENT" \
>   --name loadtest-prometheus --image prom/prometheus:latest \
>   --args '--config.file=/etc/prometheus/prometheus.yml' \
>          '--storage.tsdb.retention.time=30d' \
>          '--web.enable-remote-write-receiver' \
>   --ingress external --target-port 9090 --min-replicas 1
> ```
> Then `LOADTEST_PROMETHEUS_RW_URL=https://<fqdn>/api/v1/write` and point
> Grafana's Prometheus datasource at `https://<fqdn>`. (Add a shared-secret
> header or restrict ingress if you expose it externally.) Prefer the managed
> workspace if you can get remote-write working.

## 3. Azure Managed Grafana

**Portal:** Create a resource → **"Azure Managed Grafana"** → Create (name
`stitch-grafana`, same RG/region).

> **Two different UIs.** Steps 1 below live in the **Azure portal blade** for the
> Grafana resource. Steps 3–4 live **inside the Grafana app** — open it from the
> resource **Overview → Endpoint** link (`https://stitch-grafana-….grafana.azure.com`);
> that's where *Connections*, *Data sources*, and *Dashboards* are.

1. **Connect managed Prometheus (link it).** Two equivalent ways — either:
   - Azure Monitor Workspace `stitch-prometheus` → **Linked Grafana workspaces** →
     **+ Link** → `stitch-grafana`; or
   - the Grafana resource blade → **Integrations → Azure Monitor workspaces** →
     add `stitch-prometheus`.

   Linking auto-creates the Prometheus data source in Grafana **and** grants
   Grafana's managed identity **Monitoring Data Reader** on the workspace — no
   manual datasource config or role assignment needed.
2. **No datasource UID to reconcile.** The committed dashboards reference their
   Prometheus source through a `datasource` **template variable** (not a
   hardcoded UID), so on import Grafana auto-selects the linked Prometheus source
   (or offers a picker at the top of the dashboard). Nothing to match up.
3. **Azure Monitor datasource** (for App Insights trace drill-down), *in the
   Grafana app* → **Connections → Data sources**: Azure Managed Grafana usually
   **pre-provisions** an "Azure Monitor" datasource scoped to the subscription —
   check before adding one. Its managed identity needs **Monitoring
   Reader**/**Reader** on the App Insights resource.
4. **Import the dashboards**, *in the Grafana app* → **Dashboards → New →
   Import** → upload/paste the two JSON files from
   [`loadtest/grafana/dashboards/`](loadtest/grafana/dashboards/).

**CLI:**
```bash
az extension add -n amg --upgrade
az grafana create --name stitch-grafana -g "$RG" -l "$LOC"
GRAFANA_MI=$(az grafana show --name stitch-grafana -g "$RG" --query identity.principalId -o tsv)

# Prefer linking the workspace (Portal step 1) — it creates the Prometheus
# datasource AND grants this role automatically. Grant it explicitly only if you
# added the datasource by hand instead:
az role assignment create --assignee "$GRAFANA_MI" \
  --role "Monitoring Data Reader" --scope "$AMW_ID"

# Dashboards select their datasource via a `datasource` template variable, so
# there is no UID to match — they auto-pick the Prometheus source on import.
az grafana dashboard import --name stitch-grafana -g "$RG" \
  --definition deployments/loadtest/grafana/dashboards/k6-pr-compare.json
az grafana dashboard import --name stitch-grafana -g "$RG" \
  --definition deployments/loadtest/grafana/dashboards/api-live-red.json
```

Re-import after editing the JSON in-repo to keep Grafana in sync (dashboards are
version-controlled here, not in Grafana). The Azure Monitor datasource also needs
**Monitoring Reader** (or **Reader**) on the App Insights resource / RG.

## 4. GitHub Actions variables

The CI job runs in the **`development`** GitHub Environment. Set these as
**environment variables** there (Settings → Environments → development →
Variables), or with the CLI:

| Variable | Value |
|---|---|
| `LOADTEST_PROMETHEUS_RW_URL` | The remote-write ingestion URL from step 2. |
| `GRAFANA_URL` | `https://<grafana endpoint>` (`az grafana show … --query properties.endpoint`). |

```bash
gh variable set LOADTEST_PROMETHEUS_RW_URL --env development --body "<ingestion url>"
gh variable set GRAFANA_URL --env development --body "https://<grafana endpoint>"
```

Until `LOADTEST_PROMETHEUS_RW_URL` is set, the seed and load test still run and
print their summaries — they just don't publish (no dashboard data, and the PR
comment carries a warning). Nothing blocks a PR before this setup is done.

## 5. Optional — server-side RED (span-derived metrics) on Azure

The `api-live-red` dashboard shows rate/errors/duration derived from the API's
**spans** (no app-side metrics code), via the collector's `spanmetrics`
connector. This is **already enabled locally** (see
[`otel-collector/config.yaml`](otel-collector/config.yaml)); on Azure it is
**opt-in**, because the live per-lane collector must not point a remote-write
exporter at an endpoint that doesn't exist yet (a bad exporter stops the whole
trace pipeline).

To enable it, add to [`otel-collector/config-azure.yaml`](otel-collector/config-azure.yaml)
the same `spanmetrics` connector as the local config, plus a
`prometheusremotewrite` exporter to the workspace (Entra auth via the collector
Container App's managed identity), wired into a `metrics/spanmetrics` pipeline.
Then grant that managed identity **Monitoring Metrics Publisher** on the DCR and
set the remote-write endpoint on the collector app.

> **Caveat:** the collector is deployed **once per lane**
> (`{lane}-otel-collector`), so all `pr-{N}` apps in `development` share it and
> their spans aggregate under `service_name=stitch-api` with no per-PR label. The
> `api-live-red` dashboard is therefore a lane-wide live view, **not** per-PR. To
> separate PRs, add `deployment.environment` (already `pr-{N}` on each app) as a
> spanmetrics dimension and a Grafana template variable. Left as a follow-up.

## 6. Cost & retention

Managed Prometheus bills per sample ingested/queried. A ~90s flat-out test plus
the seed per PR is modest, but every PR adds up — set a sane retention on the
workspace (or the fallback Prometheus `--storage.tsdb.retention.time`) and
revisit if volume grows.
