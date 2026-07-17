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
   the DCR — if you're a limited admin, hand the CLI command below to someone who
   has it.
   > ⚠️ **Scope gotcha (this bit us):** the auto-created DCR does **not** live in
   > your workspace's resource group — it's in Azure's **managed** RG
   > (`MA_<workspace>_<region>_managed`, e.g. `MA_stitch-prometheus_westus2_managed`).
   > So granting the role on `STITCH-DEV-RG` does **nothing** for it; every
   > remote-write 403s. Scope the grant to the **DCR itself** (or that managed RG).
   > Find the DCR with `az monitor data-collection rule list -o table`.
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

### Alternative: your own DCE + DCR (when you can't grant on the managed DCR)

If you only have role-assignment rights in your own resource group (not the
managed `MA_…` RG where the auto-created DCR lives), you can't grant the CI
principal on that DCR. Instead, create **your own** DCE + DCR **in a RG you
control** (`STITCH-DEV-RG`) that ingests to the *same* Azure Monitor Workspace,
grant the role on your DCR, and point `LOADTEST_PROMETHEUS_RW_URL` at it.

**Portal vs CLI for each piece:**

**You do not need a new DCE** — reuse the workspace's existing managed DCE
(`stitch-prometheus`); a DCR can reference a DCE across resource groups, and only
*read* on the DCE is required. Its metrics endpoint is also the **same host**
already in your `LOADTEST_PROMETHEUS_RW_URL`, so only the DCR immutable-id segment
of the URL changes. You only create the **DCR** (in your RG, so you can grant on it).

| Piece | Portal | CLI |
|---|---|---|
| Data Collection **Endpoint** | reuse the existing managed one (no create) | — |
| Data Collection **Rule** (Prometheus remote-write) | ❌ **CLI/ARM only** — the "Create Data Collection Rule" wizard offers only *Agent-based* / *Platform telemetry*, not the Prometheus stream | ✅ (`--rule-file`) |
| Role assignment + reading the immutable ID | ✅ (DCR → IAM / JSON View) | ✅ |

**CLI** (verify field names against the `show` output — the DCR schema is
version-dependent; the surest template is the managed DCR's own JSON, below):

```bash
RG=STITCH-DEV-RG ; LOC=westus2
AMW_ID=$(az monitor account show -n stitch-prometheus -g "$RG" --query id -o tsv)

# Reuse the workspace's existing managed DCE (no new one needed):
DCE_ID=$(az monitor data-collection endpoint list \
  --query "[?name=='stitch-prometheus'].id | [0]" -o tsv)

# See the managed DCR's exact shape and mirror its dataSources/destinations/dataFlows:
az monitor data-collection rule show -n stitch-prometheus \
  -g MA_stitch-prometheus_westus2_managed

# DCR rule file targeting the workspace (mirror the managed DCR if this shape drifts)
cat > /tmp/stitch-prom-dcr.json <<JSON
{
  "location": "$LOC",
  "properties": {
    "dataCollectionEndpointId": "$DCE_ID",
    "dataSources": { "prometheusForwarder": [
      { "name": "PrometheusDataSource", "streams": ["Microsoft-PrometheusMetrics"], "labelIncludeFilter": {} }
    ] },
    "destinations": { "monitoringAccounts": [
      { "accountResourceId": "$AMW_ID", "name": "MonitoringAccount1" }
    ] },
    "dataFlows": [
      { "streams": ["Microsoft-PrometheusMetrics"], "destinations": ["MonitoringAccount1"] }
    ]
  }
}
JSON
az monitor data-collection rule create \
  --name stitch-prom-dcr -g "$RG" -l "$LOC" --rule-file /tmp/stitch-prom-dcr.json

# 3. Grant the CI principal on YOUR DCR (you own this RG, so this works)
DCR_ID=$(az monitor data-collection rule show -n stitch-prom-dcr -g "$RG" --query id -o tsv)
az role assignment create \
  --assignee-object-id <CI service principal object id> \
  --assignee-principal-type ServicePrincipal \
  --role "Monitoring Metrics Publisher" --scope "$DCR_ID"

# 4. Build LOADTEST_PROMETHEUS_RW_URL: SAME host as before (the reused managed
#    DCE's metrics endpoint), only the immutable id changes to your new DCR's.
IMMUTABLE=$(az monitor data-collection rule show -n stitch-prom-dcr -g "$RG" --query immutableId -o tsv)
# URL = https://stitch-prometheus-wxjg.westus2-1.metrics.ingest.monitor.azure.com/dataCollectionRules/$IMMUTABLE/streams/Microsoft-PrometheusMetrics/api/v1/write?api-version=2023-04-24
```

> The DCR JSON and the exact ingestion-endpoint field are the finicky, version-
> dependent bits — **base them on the managed DCR's `show` output** and current
> Microsoft docs rather than trusting the snippet verbatim. If this fights you,
> the self-hosted-Prometheus fallback below sidesteps DCE/DCR entirely.

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
3. **Azure Monitor datasource** (for the App Insights RED board + trace
   drill-down), *in the Grafana app* → **Connections → Data sources**: Azure
   Managed Grafana usually **pre-provisions** an "Azure Monitor" datasource —
   check before adding one.
   > ⚠️ **Separate grant, easy to miss (this bit us):** linking the Prometheus
   > workspace (step 1) grants read to *Prometheus only*. To read **App Insights**,
   > Grafana's managed identity needs **Monitoring Reader** on the App Insights
   > resource (or its RG). Without it the RED board shows red ⚠️ panels with
   > `InsufficientAccessToResource`. Grant it (App Insights is in `STITCH-DEV-RG`,
   > so an RG-scoped grant works and you can do it yourself):
   > ```bash
   > GRAFANA_MI=$(az grafana show -n stitch-grafana -g STITCH-DEV-RG --query identity.principalId -o tsv)
   > az role assignment create --assignee-object-id "$GRAFANA_MI" \
   >   --assignee-principal-type ServicePrincipal --role "Monitoring Reader" \
   >   --scope "/subscriptions/<sub>/resourceGroups/STITCH-DEV-RG"
   > ```
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

# Dashboards select their datasource via a `datasource` template variable (no UID
# to match): k6-pr-compare auto-picks Prometheus; api-live-red auto-picks Azure
# Monitor (set its `appinsights` variable to the App Insights resource ID).
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

## 5. Server-side RED (from Application Insights — no collector changes)

The `api-live-red` dashboard shows per-PR rate/errors/duration for the API. It
reads the **request spans already flowing to Application Insights** (stamped with
`deployment.name=pr-<N>` via `OTEL_RESOURCE_ATTRIBUTES` in CI) and queries them
with **KQL through Grafana's Azure Monitor datasource** — so there are **no
collector changes**, no `prometheusremotewrite` auth, and no risk to the live
trace pipeline.

Why this and not span-derived Prometheus metrics: the OTel collector is deployed
**once per lane** (`{lane}-otel-collector`, shared by every `pr-{N}` in the
lane), and making it remote-write to managed Prometheus would need continuous
Azure auth (a static service-principal secret via `oauth2client`) plus edits to
the live `config-azure.yaml`. App Insights already has the per-PR data, so we
query it directly instead. (The flat-out k6 comparison stays on managed
Prometheus, where sampling can't thin the numbers; App Insights is for
server-side per-request detail and drill-down.)

**Setup:**
1. In Grafana, ensure the **Azure Monitor** datasource exists (usually
   pre-provisioned by Azure Managed Grafana; see Step 3). Its managed identity
   needs **Monitoring Reader** / **Reader** on the App Insights resource / RG.
2. Import `api-live-red.json` (done in Step 3). It has two variables:
   - `datasource` → pick the Azure Monitor datasource (auto-selected).
   - `appinsights` → paste the **App Insights resource ID** (Portal → App
     Insights → Settings → Properties → Resource ID). The KQL queries target it.
3. Data appears once PR traffic (or a load test) has hit the deployed API and
   spans have flowed to App Insights.

> **Note:** App Insights applies adaptive sampling under heavy load, so treat
> these numbers as representative of normal/PR traffic — the flat-out k6 test's
> authoritative numbers live in the Prometheus `k6-pr-compare` dashboard. If you
> need exact server-side percentiles under load, lower sampling on the dev lane.

## 6. Cost & retention

Managed Prometheus bills per sample ingested/queried. A ~90s flat-out test plus
the seed per PR is modest, but every PR adds up — set a sane retention on the
workspace (or the fallback Prometheus `--storage.tsdb.retention.time`) and
revisit if volume grows.
