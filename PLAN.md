# OTel on Azure — Plan

## Context

All Stitch services have OpenTelemetry tracing instrumented via `stitch-observability`. Locally,
`OTEL_TRACES_EXPORTER=otlp` ships spans to an OTel Collector → Jaeger. In Azure, no `OTEL_TRACES_EXPORTER`
is set, so services fall back to `console` (spans go to stdout as structured JSON, but are not queryable
as traces). This plan wires up a real trace backend in Azure: a per-lane OTel Collector Container App
that forwards to Azure Monitor / Application Insights.

---

## Azure Architecture

### Log Analytics + Application Insights topology
- **One shared Log Analytics Workspace** (e.g., `stitch-logs`) — all lanes write here
- **One Application Insights resource per lane**, in workspace-based mode:
  - `stitch-appinsights-development`
  - `stitch-appinsights-staging`
  - `stitch-appinsights-production` (dress-rehearsal lane)
- Each App Insights has its own `Connection String` → stored as lane-scoped secret `APPLICATIONINSIGHTS_CONNECTION_STRING`
- Cross-lane comparison is done in the shared workspace via Kusto, filtering on `cloud_RoleInstance`
  (which maps to `deployment.environment` from the OTel resource attributes)

### RBAC
- Shared workspace: all developers get **Reader** at the workspace level (read-only cross-lane queries)
- Dev + Staging App Insights: all developers get **Monitoring Reader**
- Production App Insights: restrict to a dedicated security group / on-call rotation via **Monitoring Reader**

### PII strategy (two-phase)
- **Phase 1 (this PR):** document that PII should not be placed in span attributes; rely on RBAC for prod
- **Phase 2 (follow-up):** add an OTel `attributes` processor in the production collector config to
  redact or drop fields that may carry PII (e.g. `http.url` query strings, `db.statement` if it logs
  user data)

---

## Manual Azure Provisioning (one-time, per environment)

Run these steps in the Azure portal or via the Azure CLI. Do this before merging the CI changes.

```bash
# 1. Create a shared Log Analytics Workspace (once, in the shared resource group)
az monitor log-analytics workspace create \
  --resource-group <shared-rg> \
  --workspace-name stitch-logs \
  --location <region>

WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group <shared-rg> \
  --workspace-name stitch-logs \
  --query id -o tsv)

# 2. Repeat for each lane (development, staging, dress-rehearsal)
LANE=development   # or staging / dress-rehearsal
az monitor app-insights component create \
  --app stitch-appinsights-${LANE} \
  --resource-group <lane-resource-group> \
  --location <region> \
  --workspace ${WORKSPACE_ID} \
  --kind web \
  --application-type web

# 3. Get the connection string and store as a GitHub environment secret
az monitor app-insights component show \
  --app stitch-appinsights-${LANE} \
  --resource-group <lane-resource-group> \
  --query connectionString -o tsv
# → paste into GitHub Environment secret: APPLICATIONINSIGHTS_CONNECTION_STRING
```

Repeat step 2–3 for each lane. Each lane's secret value is different.

---

## Code Changes

### 1. `deployments/otel-collector/config-azure.yaml` (new file)

OTel Collector config for Azure. Uses env var substitution for the connection string.

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch: {}

exporters:
  azuremonitor:
    connection_string: ${APPLICATIONINSIGHTS_CONNECTION_STRING}
  debug:
    verbosity: normal

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [azuremonitor, debug]
```

### 2. `deployments/otel-collector/Dockerfile` (new file)

Bakes the Azure config into the public contrib image. Connection string is NOT in the image.

```dockerfile
FROM otel/opentelemetry-collector-contrib:0.127.0
COPY config-azure.yaml /etc/otel-collector-config.yaml
CMD ["--config=/etc/otel-collector-config.yaml"]
```

Pin to a specific version tag (not `latest`) for reproducible deploys.

### 3. `packages/stitch-observability/src/stitch/observability/settings.py`

Add `otel_exporter_otlp_protocol` to `OTelSettings`. Pydantic-settings reads this from
`OTEL_EXPORTER_OTLP_PROTOCOL` automatically.

```python
otel_exporter_otlp_protocol: Literal["grpc", "http"] = "grpc"
```

### 4. `packages/stitch-observability/src/stitch/observability/tracing.py`

Add HTTP exporter branch in `configure_tracing`. The HTTP endpoint needs a `/v1/traces` path suffix.

```python
if exporter == "otlp":
    if protocol == "http":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as OTLPHttpSpanExporter,
        )
        http_endpoint = otlp_endpoint  # caller passes full URL incl. /v1/traces
        span_exporter = OTLPHttpSpanExporter(endpoint=http_endpoint)
    else:
        span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    provider.add_span_processor(BatchSpanProcessor(span_exporter))
```

Update `configure_tracing` signature to accept `protocol: str = "grpc"`.

### 5. `packages/stitch-observability/pyproject.toml`

Add HTTP exporter dependency alongside the existing gRPC one:

```toml
"opentelemetry-exporter-otlp-proto-http>=1.30.0",
```

### 6. `.github/workflows/deploy-container.yml`

Add an optional secret and wire it into the env var assembly step:

```yaml
secrets:
  # ... existing secrets ...
  applicationinsights-connection-string:
    required: false
```

In "Assemble environment variables":
```bash
APPINSIGHTS_CONNECTION_STRING: ${{ secrets.applicationinsights-connection-string }}
# ...
if [ -n "${APPINSIGHTS_CONNECTION_STRING:-}" ]; then
  envvars="$envvars APPLICATIONINSIGHTS_CONNECTION_STRING=${APPINSIGHTS_CONNECTION_STRING}"
fi
```

### 7. `.github/workflows/build-and-deploy.yml`

#### New job: `build-otel-collector-docker-image`
Runs in parallel with other build jobs.

```yaml
build-otel-collector-docker-image:
  name: "Build and publish OTel Collector"
  needs: [resolve-context]
  uses: ./.github/workflows/build-and-push-Docker-image.yml
  secrets: inherit
  permissions:
    packages: write
    contents: read
  with:
    dockerfile: deployments/otel-collector/Dockerfile
    image-name: ${{ github.event.repository.name }}-otel-collector
    image-tag: ${{ needs.resolve-context.outputs.deployment-name }}
```

#### New job: `deploy-otel-collector`
Lane-scoped name (stable across PRs in the same lane). Always min-replicas=1.

```yaml
deploy-otel-collector:
  name: "Deploy OTel Collector"
  needs: [resolve-context, build-otel-collector-docker-image]
  uses: ./.github/workflows/deploy-container.yml
  secrets:
    azure-client-id: ${{ secrets.AZURE_CLIENT_ID }}
    azure-tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    azure-subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    applicationinsights-connection-string: ${{ secrets.APPLICATIONINSIGHTS_CONNECTION_STRING }}
  with:
    deployment-lane: ${{ needs.resolve-context.outputs.deployment-lane }}
    full-image-name: ${{ needs.build-otel-collector-docker-image.outputs.digest-image-name }}
    container-app-name: ${{ format('{0}-otel-collector', needs.resolve-context.outputs.deployment-lane) }}
    target-port: 4318
    deployment-label: otel-collector
    min-replicas: "1"
    environment-variables: ""
```

Note: `container-app-name` uses `deployment-lane` (not `deployment-name`) so all PRs in dev share one collector.

#### Wire OTEL env vars into service deploys

Add to `deploy-api`, `deploy-entity-linkage`, `deploy-stitch-llm` environment-variables and needs:

```yaml
deploy-api:
  needs: [..., deploy-otel-collector]   # add this
  with:
    environment-variables: >-
      ...existing vars...
      OTEL_TRACES_EXPORTER=otlp
      OTEL_EXPORTER_OTLP_PROTOCOL=http
      OTEL_EXPORTER_OTLP_ENDPOINT=${{ format('{0}/v1/traces', needs.deploy-otel-collector.outputs.container-app-url) }}
```

Same pattern for `deploy-entity-linkage` and `deploy-stitch-llm`.

#### `lane-config-validate` — optional validation
Optionally warn (not fail) if `APPLICATIONINSIGHTS_CONNECTION_STRING` is unset, since existing lanes may not have it yet when this first merges.

---

## Dependency Graph (updated)

```
resolve-context → build-otel-collector-docker-image → deploy-otel-collector ─┐
               → build-api-docker-image                                        ├→ deploy-api → ...
               → deploy-db → run-db-migrations ────────────────────────────────┘
```

---

## Verification

1. **Local unit tests** (no change needed — protocol=grpc default, tests use `OTEL_TRACES_EXPORTER=none`)
2. **After merge:** open Azure portal → Application Insights → Live Metrics or Transaction Search → make a request to the deployed API → verify a trace appears within ~30s
3. **Cross-lane query** in Log Analytics workspace:
   ```kusto
   union app('stitch-appinsights-development').requests,
         app('stitch-appinsights-staging').requests
   | where timestamp > ago(1h)
   | summarize count() by cloud_RoleInstance
   ```
4. **Confirm collector is alive:** `az containerapp show --name development-otel-collector ...` should show `runningStatus: Running`
