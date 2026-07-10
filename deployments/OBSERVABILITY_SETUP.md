# Observability setup — Grafana + managed Prometheus (one-time, by hand)

This is the **one-time** cloud setup behind the per-PR load-test dashboards. The
repo commits the dashboards and the CI job; the shared, long-lived resources
below are provisioned by hand (no IaC in this repo) and recorded here so the
setup is reproducible.

You only run this once per Azure environment. Day-to-day, the
[`run-perf.yml`](.github/workflows/run-perf.yml) CI job publishes to what you
provision here, and you read the results in Grafana (see
[`PERFORMANCE.md`](PERFORMANCE.md)).

## What you're building

```
k6 (GitHub runner) ──remote-write (Entra token)──► Azure Monitor Workspace
                                                     (managed Prometheus)
                                                          ▲ PromQL
Application Insights ◄── (already exists, traces) ── Azure Managed Grafana
                                                     ├ datasource: Prometheus (uid: stitch-prometheus)
                                                     └ datasource: Azure Monitor (App Insights)
```

Already in place (prereqs — do not recreate): the resource group
(`AZURE_RESOURCE_GROUP`), the Container Apps environment
(`AZURE_CONTAINER_APP_ENVIRONMENT`), Application Insights
(`APPLICATIONINSIGHTS_CONNECTION_STRING`), and the CI OIDC service principal
(`AZURE_CLIENT_ID`). Set the shell vars below before running the commands:

```bash
RG="<AZURE_RESOURCE_GROUP>"
LOC="<region, e.g. eastus>"
CI_PRINCIPAL="<AZURE_CLIENT_ID>"          # the OIDC app the CD pipeline logs in as
```

## 1. Azure Monitor Workspace (managed Prometheus)

```bash
az monitor account create --name stitch-prometheus -g "$RG" -l "$LOC"
AMW_ID=$(az monitor account show --name stitch-prometheus -g "$RG" --query id -o tsv)
```

Note its **metrics ingestion endpoint** and **query endpoint** from
`az monitor account show --name stitch-prometheus -g "$RG"` — you'll need the
ingestion endpoint for step 2 and the query endpoint is used by Grafana in
step 3.

## 2. Remote-write ingestion (the fiddly part)

k6 must push its metrics into the workspace via Prometheus remote-write,
authenticated with an **Entra token** for resource `https://monitor.azure.com`
(the CI job already mints this with `az account get-access-token`).

The exact remote-write ingestion path for a standalone (non-AKS) writer on
Azure Monitor Workspace is **version-dependent** — it goes through a Data
Collection Endpoint (DCE) + Data Collection Rule (DCR), and the URL shape has
changed across API versions. Follow current Microsoft docs for "send Prometheus
remote-write to Azure Monitor Workspace", then:

1. Create the DCE + DCR targeting `stitch-prometheus`.
2. Grant the **CI principal** the **Monitoring Metrics Publisher** role on the
   DCR (so the runner's token can ingest):
   ```bash
   az role assignment create \
     --assignee "$CI_PRINCIPAL" \
     --role "Monitoring Metrics Publisher" \
     --scope "<DCR resource id>"
   ```
3. Capture the full remote-write URL (the `.../api/v1/write` ingestion URL) — it
   becomes `LOADTEST_PROMETHEUS_RW_URL` in step 4.

> **If this proves fiddly, use the fallback** — it is fully self-contained and
> guaranteed to work with k6 remote-write + Grafana. Stand up a small Prometheus
> as its own Container App in the existing environment:
> ```bash
> az containerapp create -g "$RG" \
>   --environment "$AZURE_CONTAINER_APP_ENVIRONMENT" \
>   --name loadtest-prometheus \
>   --image prom/prometheus:latest \
>   --args '--config.file=/etc/prometheus/prometheus.yml' \
>          '--storage.tsdb.retention.time=30d' \
>          '--web.enable-remote-write-receiver' \
>   --ingress internal --target-port 9090 --min-replicas 1
> ```
> Then `LOADTEST_PROMETHEUS_RW_URL=http://loadtest-prometheus/api/v1/write`
> (internal ingress, reachable from the runner only if the runner is in-network —
> otherwise use external ingress + a shared-secret header). Point Grafana's
> Prometheus datasource at `http://loadtest-prometheus:9090`. This trades the
> managed workspace for a single always-on container you operate yourself; retention
> is whatever you set on the flag. Prefer the managed workspace if you can get
> remote-write working.

## 3. Azure Managed Grafana

```bash
az extension add -n amg --upgrade
az grafana create --name stitch-grafana -g "$RG" -l "$LOC"
GRAFANA_ID=$(az grafana show --name stitch-grafana -g "$RG" --query id -o tsv)
```

**Datasources** (Grafana → Connections → Data sources):

- **Prometheus** — point at the workspace's query endpoint (step 1). Set its
  **UID to `stitch-prometheus`** — the committed dashboards reference that UID.
  Grafana's managed identity needs the **Monitoring Data Reader** role on the
  workspace to query it:
  ```bash
  GRAFANA_MI=$(az grafana show --name stitch-grafana -g "$RG" \
    --query identity.principalId -o tsv)
  az role assignment create --assignee "$GRAFANA_MI" \
    --role "Monitoring Data Reader" --scope "$AMW_ID"
  ```
- **Azure Monitor** — the built-in datasource, scoped to the subscription/RG, for
  drilling from a Prometheus regression into the App Insights trace. Grafana's
  managed identity needs **Monitoring Reader** / **Reader** on the App Insights
  resource (or RG).

**Import the dashboards** (committed in
[`loadtest/grafana/dashboards/`](loadtest/grafana/dashboards/)):

```bash
az grafana dashboard import --name stitch-grafana -g "$RG" \
  --definition deployments/loadtest/grafana/dashboards/k6-pr-compare.json
az grafana dashboard import --name stitch-grafana -g "$RG" \
  --definition deployments/loadtest/grafana/dashboards/api-live-red.json
```

Re-import after editing the JSON in-repo to keep Grafana in sync (dashboards are
version-controlled here, not in Grafana).

## 4. GitHub Actions variables

The CI job runs in the **`development`** GitHub Environment. Set these as
**environment variables** on that environment (Settings → Environments →
development → Variables):

| Variable | Value |
|---|---|
| `LOADTEST_PROMETHEUS_RW_URL` | The remote-write ingestion URL from step 2. |
| `GRAFANA_URL` | `https://<stitch-grafana endpoint>` (from `az grafana show ... --query properties.endpoint`). |

Until `LOADTEST_PROMETHEUS_RW_URL` is set, the load test still runs each PR and
prints its summary — it just doesn't publish (no dashboard data, and the PR
comment carries a warning). Nothing blocks a PR before this setup is done.

## 5. Optional — server-side RED (span-derived metrics)

The `api-live-red` dashboard shows rate/errors/duration derived from the API's
**spans** (no app-side metrics code), via the collector's `spanmetrics`
connector. It is **not enabled by default** because the live per-lane collector
must not point a remote-write exporter at an endpoint that doesn't exist yet
(a bad exporter stops the whole trace pipeline).

To enable it, add to [`otel-collector/config-azure.yaml`](otel-collector/config-azure.yaml):

```yaml
connectors:
  spanmetrics:
    namespace: spanmetrics
    histogram:
      unit: ms
      explicit:
        buckets: [5ms, 10ms, 25ms, 50ms, 75ms, 100ms, 250ms, 500ms, 750ms, 1s, 2500ms, 5s, 10s]
    dimensions:
      - name: http.route
      - name: http.request.method
      - name: http.response.status_code
    exemplars:
      enabled: false
    metrics_flush_interval: 15s

exporters:
  # ... existing azuremonitor, debug ...
  prometheusremotewrite:
    endpoint: ${PROMETHEUS_REMOTE_WRITE_ENDPOINT}   # the workspace ingestion URL
    auth:
      authenticator: oauth2client   # Entra token; configure via the collector's managed identity

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [azuremonitor, debug, spanmetrics]  # spanmetrics = connector input
    metrics/spanmetrics:
      receivers: [spanmetrics]
      processors: [batch]
      exporters: [prometheusremotewrite]
```

Then: grant the collector Container App's managed identity **Monitoring Metrics
Publisher** on the DCR, and set `PROMETHEUS_REMOTE_WRITE_ENDPOINT` on the
collector app.

> **Caveat:** the collector is deployed **once per lane**
> (`{lane}-otel-collector`), so all `pr-{N}` apps in `development` share it and
> their spans aggregate under `service_name=stitch-api` with no per-PR label. The
> `api-live-red` dashboard is therefore a lane-wide live view, **not** per-PR. To
> separate PRs, add `deployment.environment` (already set to `pr-{N}` on each app)
> as a spanmetrics dimension and a Grafana template variable. Left as a follow-up.

## 6. Cost & retention

Managed Prometheus bills per sample ingested/queried. A 1–2 min flat-out test
per PR is modest, but every PR adds up — set a sane retention on the workspace
(or the fallback Prometheus `--storage.tsdb.retention.time`) and revisit if
volume grows.
