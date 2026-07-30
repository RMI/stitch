# CI/CD Deployments

The CD pipeline is managed by the GitHub workflow `build-and-deploy.yml`.

It uses two explicit workflow concepts:

- `deployment_lane`: deploy class / GitHub Environment name
- `deployment_name`: concrete runtime target name used for DB and app naming

Branch behavior is:

- push to `main` -> `deployment_lane=development`, `deployment_name=main`
- any PR not targeting `production` -> `deployment_lane=development`, `deployment_name=pr-<number>`
- push to `production` -> `deployment_lane=dress-rehearsal`, `deployment_name=production`
- any PR targeting `production` -> `deployment_lane=staging`, branch-derived `deployment_name`
- any PR from a `demo/*` branch -> `deployment_lane=staging`, branch-derived `deployment_name` (regardless of whether it targets `main` or `production`)

Examples:

- PR #57 into `main` -> `deployment_name=pr-57`
- PR from `next` into `production` -> `deployment_name=next`
- PR from `hotfix/fix-auth` into `production` -> `deployment_name=hotfix-fix-auth`
- PR from `demo/q3-pitch` into `main` -> `deployment_name=demo-q3-pitch`

It builds Docker images for:

- `api` (also used for DB migration)
- `entity-linkage`
- `stitch-llm`
- `seed`

It then handles deployments for:

- the database, assuming an existing Azure PostgreSQL flexible server
- the API Container App, assuming an existing Container Apps environment
- the entity-linkage Container App in the same environment
- the stitch-llm Container App in the same environment
- the ETL Container App (`etl`) in the same environment, on non-`development`
  lanes only (see below)

### ETL pipelines (temporary POC wiring)

The single `etl` Container App is deployed from a pre-built image published by
the separate `stitch-etl-poc` repository (`ghcr.io/rmi/stitch-etl-poc`). This
pipeline does **not** build it; it only deploys the tag named by the
`ETL_IMAGE_TAG` variable (defaulting to `main`). The one app serves both
datasets under `/api/v1/etl/gem/*` and `/api/v1/etl/wm/*`.

Because it validates every dataset's config at startup (fail-fast), the app
**requires `WOODMAC_API_KEY` to boot at all** — even for GEM-only runs. The
`deploy-etl` job therefore always passes it.

Seed and ETL are mutually exclusive per lane:

- `development`: `seed` builds and runs; ETL deploy is skipped.
- `staging` / `dress-rehearsal`: ETL deploys; `seed` is skipped.

Because the ETL image lives in another repo's GHCR, the Container App needs
stored pull credentials. The ephemeral `GITHUB_TOKEN` cannot be used (it expires
and the app re-pulls on every restart), so a long-lived classic PAT with
`read:packages` is required — GHCR does not support fine-grained tokens. These
are supplied to `deploy-container.yml` via the `registry-server` /
`registry-username` inputs and the `registry-password` secret. The frontend
receives the single ETL Container App URL (empty when not deployed) and renders
the ETL control page.

CORS: the ETL app allows exactly one browser origin, set at deploy time via
`ETL_FRONTEND_ORIGIN_URL` (sourced from the lane's computed
`frontend-origin-url`). Unset, it defaults to `http://localhost:3000`, so a
missing value shows up as a browser CORS ("No 'Access-Control-Allow-Origin'
header") failure, not a server error.

#### ETL durable storage (Azure Files — wired in CI; storage prerequisites manual)

The ETL app mounts a persistent **SMB Azure Files** share so its data survives
restarts/revisions: the `etl` app reads its GEM reference spreadsheet from
`GEM_FILE_DIR=/mnt/data/gem` and keeps the WoodMac cache at
`WOODMAC_DATA_DIR=/mnt/data/woodmac`. One share per lane is mounted into the app
at `/mnt/data`, with each dataset using its own subfolder (`gem/`, `woodmac/`).

The **per-app mount is applied automatically by the pipeline** —
`azure/container-apps-deploy-action@v1` can't mount volumes, so
`deploy-container.yml` takes optional `storage-name` / `storage-mount-path` inputs
and, after the deploy, reads the app spec (`az containerapp show`), injects the
volume + volumeMount with `jq`, and re-applies it (`az containerapp update
--yaml`). The `deploy-etl` job passes `storage-name` (from the lane's `ETL_STORAGE_NAME`
variable, routed via `lane-config-validate` because env-scoped variables aren't
visible to reusable-workflow callers) and `storage-mount-path: /mnt/data`. Because
it runs every deploy, **do not configure the mount by hand in the Portal** — the
pipeline reasserts it and a manual mount would just be overwritten.

What _is_ manual is the storage itself. Do the steps below in the **Azure Portal**
(no `az` needed; SMB registration and mounting are fully Portal-supported — only
NFS forces CLI/YAML) per lane (`staging`, `dress-rehearsal`), in that lane's
resource group and Container Apps environment. Each lane gets its own storage
account / share / environment-storage name:

| Lane              | Storage account | File share            | Env storage name (`ETL_STORAGE_NAME`) |
| ----------------- | --------------- | --------------------- | ------------------------------------- |
| `staging`         | `stitchstaging` | `etl-staging`         | `etl-staging`                         |
| `dress-rehearsal` | `stitchstaging` | `etl-dress-rehearsal` | `etl-dress-rehearsal`                 |

1. **Create a storage account + file share.** Create a Storage account (Standard
   LRS, StorageV2) or reuse one, then under **File shares** add a share (for
   `staging`: account `stitchstaging`, share `etl-staging`).

2. **Create the subfolders and upload data.** In the share's **Browse** view,
   create a `gem/` folder and upload the GEM reference spreadsheet
   (`Global-Oil-and-Gas-Extraction-Tracker-*.xlsx`) into it, and create a
   `woodmac/` folder for the cache (and any woodmac seed files). These match
   `GEM_FILE_DIR=/mnt/data/gem` and `WOODMAC_DATA_DIR=/mnt/data/woodmac`. The data
   is intentionally **not** baked into the image.

3. **Register the share on the Container Apps environment.** Open the Container
   Apps **Environment** → **Settings → Volume mounts → Add** → choose **SMB**, and
   enter the storage account name, account key, share name (`etl-staging` for
   staging), and access mode `ReadWrite`; name the environment storage to match
   (`etl-staging`) — this exact name is what `ETL_STORAGE_NAME` must hold. The
   registration lives on the _environment_ and persists across app deploys.
   (Container Apps does not support managed-identity access to Azure Files, so the
   account key is required regardless of Portal vs. CLI.)

   To get the account key: go to the **storage account** → **Security +
   networking → Access keys** → **Show** under `key1` and copy the **Key** value
   (either `key1` or `key2` works). Treat it as a secret — it grants full access to
   the storage account; rotate via the same blade if exposed. It is only used here
   for the manual registration; the pipeline does **not** need it as a GitHub
   secret (it references the share by the registered env-storage name).

4. **Set the `ETL_STORAGE_NAME` environment variable** (GitHub Environment →
   Variables) to the env-storage name from step 3, e.g. `etl-staging`. This is the
   one piece of GitHub config the CI wiring consumes; the share name and account
   key are used only during the manual registration above.

Equivalent CLI for step 3, for reference:

```bash
# staging values shown
az containerapp env storage set \
  --name <AZURE_CONTAINER_APP_ENVIRONMENT> \
  --resource-group <AZURE_RESOURCE_GROUP> \
  --storage-name etl-staging \
  --azure-file-account-name stitchstaging \
  --azure-file-account-key <key> \
  --azure-file-share-name etl-staging \
  --access-mode ReadWrite
```

See the Microsoft docs for the full Portal walkthrough:
<https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts-azure-files>.

#### ETL replica pinning (wired in CI)

The ETL app must run a **single replica**: it holds per-dataset job state in
memory (the `/status` endpoints) and runs one job per dataset at a time, so a
second replica would fragment status responses and (once the share is mounted)
create a concurrent writer.

This is **enforced on every deploy**, not as a one-time manual setting. The
`azure/container-apps-deploy-action@v1` step (`az containerapp up`) does not
reliably preserve scale settings, so a value set by hand in the Portal can be
reset on the next pipeline run. Instead, `deploy-container.yml` takes optional
`min-replicas` / `max-replicas` inputs and, when either is set, runs a post-deploy
`az containerapp update --min-replicas … --max-replicas …` to reassert them. The
`deploy-etl` job passes `min-replicas: "1"` and `max-replicas: "1"`, so the pin is
self-healing — no manual Portal step needed, and it survives every redeploy.

#### Container CPU / memory sizing (wired in CI)

Like replica scaling, per-app CPU and memory are reasserted after deploy rather
than left to the action's defaults (~0.5 vCPU / 1 GiB). `deploy-container.yml`
takes optional `cpu` / `memory` inputs and folds them into the same post-deploy
`az containerapp update` that pins replicas. `entity-linkage` and the `etl` app
are unoptimized and need more memory, so both pass `cpu: "2.0"` /
`memory: "4.0Gi"`.

On the default **Consumption** workload profile, CPU and memory are not
independent — only fixed pairs are valid, with memory (Gi) = 2× vCPU. So **4.0Gi
is only reachable at 2.0 vCPU**; there is no "low CPU + 4 GiB" option without
moving the environment to a Dedicated workload profile. The inputs must be set
together (the deploy validates one-without-the-other and fails fast).

#### Keeping staging / dress-rehearsal awake (scale-to-zero policy)

By default a Container App scales to zero (`min-replicas: 0`) when idle, so the
first request after a quiet period pays a cold-start. That is fine for
`development` (keeps costs down when nobody is using it) but undesirable for
`staging` / `dress-rehearsal`, which we want responsive.

The always-on services — `api`, `entity-linkage`, `stitch-llm` — therefore pass a
**lane-conditional** `min-replicas` through the same mechanism:

```yaml
min-replicas: ${{ needs.resolve-context.outputs.deployment-lane != 'development' && '1' || '' }}
```

So on `staging` / `dress-rehearsal` they reassert `min-replicas: 1` (always one
warm replica, `max` left at the default so they can still scale out), and on
`development` the input is empty, the post-deploy step is skipped, and they keep
the default scale-to-zero. The ETL app is always-on on those lanes too, since it
pins `min = max = 1` and only deploys on non-`development` lanes.

This only affects the Container Apps. The frontend is an Azure Static Web App
(always served, no hibernation), and the PostgreSQL flexible server's
pause behavior, if any, is a separate server-level setting not managed here.

#### Migration from the multi-deployment ETL topology (one-time)

The ETL wiring was consolidated from two apps (`etl-gem`, `etl-woodmac`, two
images) to one (`etl`, one image). To migrate a lane safely:

1. Merge the consolidation to `stitch-etl-poc` `main` first, so
   `ghcr.io/rmi/stitch-etl-poc:main` is published before this repo references it.
2. On the lane's GitHub Environment, add `ETL_IMAGE_TAG` (`main`) and delete the
   old `ETL_GEM_IMAGE_TAG` / `ETL_WOODMAC_IMAGE_TAG` variables.
3. Deploy this repo; confirm the new `<name>-etl` app is healthy
   (`GET …/api/v1/etl/health/details`) and that GEM and WoodMac runs work from
   the frontend.
4. Delete the now-orphaned old apps (they pin `min=max=1`, so they keep billing
   until removed):

   ```bash
   az containerapp delete -g <AZURE_RESOURCE_GROUP> -n <name>-etl-gem --yes
   az containerapp delete -g <AZURE_RESOURCE_GROUP> -n <name>-etl-woodmac --yes
   ```

   Do this in `staging` (its `deployment-name`) and for `production` /
   `dress-rehearsal`.

5. Any open PR-into-`production` environment created before this change may
   still have `-etl-gem` / `-etl-woodmac` apps; the collapsed
   `close-ci-environment` job won't remove them, so delete them by hand with the
   commands above.

Reusable workflows now select lane-specific configuration from GitHub
Environments and are expected to fail loudly when required values are absent.

The top-level deploy workflow also performs early lane validation before API and
frontend deploys proceed.

Backend infrastructure (static resources like PostgreSQL server or Continer App
environment) are shared within a deploy lane (all `development` lane
deployments, `pr-*`, `main` deploy to the same PostgreSQL instance, with
separate logical DBs)

It also handles running `db-migrations` (via Alembic in the `api` image) and
`seed`, both directly from GH Actions (rather than starting on Azure).

## Azure Permissions

Permissions for Azure Resources are handled through a managed identity, which GH
Actions runners use with `Azure/login` step.
For this repo, we're using `GHActions-stitch-cicd`.

The repo secrets must point at that exact identity:

- `AZURE_CLIENT_ID`: managed identity client ID
- `AZURE_SUBSCRIPTION_ID`: Azure subscription containing the target resources
- `AZURE_TENANT_ID`: tenant for the managed identity

Note that federated identity records for this GitHub repository need to be
added to the managed identity. For the current workflows, the required subjects
are:

- `repo:RMI/stitch:pull_request`
- `repo:RMI/stitch:ref:refs/heads/main`
- `repo:RMI/stitch:ref:refs/heads/production`
- `repo:RMI/stitch:environment:development`
- `repo:RMI/stitch:environment:staging`
- `repo:RMI/stitch:environment:dress-rehearsal`

The branch / PR subjects cover workflows that authenticate outside a GitHub
Environment. The `environment:*` subjects are also required because the
lane-scoped deploy jobs authenticate from GitHub Environments named
`development`, `staging`, and `dress-rehearsal`.

All federated credential fields must match exactly:

- Issuer: `https://token.actions.githubusercontent.com`
- Audience: `api://AzureADTokenExchange`
- Subject: case-sensitive exact match

If Azure starts returning `AADSTS7002138`, recreating the affected federated
credential is usually faster than editing it in place.

Managed identity roles:

- `Reader` on `stitch-dev` (Container Apps Environment)
- `Reader` on `STITCH-DEV-RG` (Resource Group)
- `Container Apps Contributor` on `STITCH-DEV-RG` (Resource Group)

## Setup Notes

In repo settings, under `Secrets and variables` > `Actions`, add Azure identity
secrets, then define lane-scoped variables and secrets in GitHub Environments
named:

- `development`
- `staging`
- `dress-rehearsal`

### Repo-level secrets

- `AZURE_CLIENT_ID`: Client ID for `GHActions-stitch-cicd`
- `AZURE_SUBSCRIPTION_ID`: Subscription for the target Azure resources
- `AZURE_TENANT_ID`: Tenant for `GHActions-stitch-cicd`

### Environment variables

- `AZURE_RESOURCE_GROUP` (example: `STITCH-DEV-RG`)
- `AZURE_CONTAINER_APP_ENVIRONMENT` (example: `stitch-dev`)
- `POSTGRES_HOST` (example: `stitch-dev.postgres.database.azure.com`)
- `POSTGRES_PORT` (example: `5432`)
- `POSTGRES_ADMIN_USER` (example: `postgres`)
- `POSTGRES_SSLMODE` (example: `require`)
- `POSTGRES_DEFAULT_DB` (example: `postgres`)
- `FRONTEND_PRODUCTION_URL` (example: `https://witty-mushroom-017a3dc1e.1.azurestaticapps.net`)
- `FRONTEND_PREVIEW_URL_TEMPLATE` (example: `https://witty-mushroom-017a3dc1e-{name}.westus2.1.azurestaticapps.net`)
- `AUTH_DISABLED` (example: `true` for `development`, `false` for `staging` / `dress-rehearsal`)
- `AUTH_ISSUER` (example: `https://rmi-spd.us.auth0.com/`)
- `AUTH_AUDIENCE` (example: `https://stitch-api.local`)
- `AUTH_JWKS_URI` (example: `https://rmi-spd.us.auth0.com/.well-known/jwks.json`)
- `AUTH0_DOMAIN` (example: `rmi-spd.us.auth0.com`)
- `AUTH0_CLIENT_ID` (example: `<public-client-id>`)
- `AUTH0_AUDIENCE` (example: `https://stitch-api.local`)
- `STITCH_LLM_AZURE_OPENAI_BASE_URL` (example: `https://stitch-foundry-dev.openai.azure.com/openai/v1`)
- `STITCH_LLM_AZURE_OPENAI_MODEL` (example: `gpt-5.1-chat`)
- `STITCH_LLM_AZURE_OPENAI_TIMEOUT_SECONDS` (example: `30`)
- `GHCR_ETL_PULL_USERNAME` (example: `your-github-username`) — registry username
  for pulling the ETL image; not sensitive, so it is a variable. Only needed on
  `staging` / `dress-rehearsal`.
- `ETL_STORAGE_NAME` (example: `etl-staging`) — the Azure Files env-storage name
  registered on the Container Apps environment; mounted into the `etl` app at
  `/mnt/data`. Only needed on `staging` / `dress-rehearsal` (see ETL durable
  storage above).
- `ETL_IMAGE_TAG` (example: `main`) — optional; consolidated ETL image tag to
  deploy, defaults to `main`. Only used on `staging` / `dress-rehearsal`.
  - NOTE: `FRONTEND_PREVIEW_URL_TEMPLATE` must contain the literal `{name}` placeholder.
    For `dress-rehearsal`, the workflow uses `FRONTEND_PRODUCTION_URL` directly. For pull requests, it replaces `{name}` with the raw PR number so PR #106 resolves to `https://witty-mushroom-017a3dc1e-106.westus2.1.azurestaticapps.net`. For other preview deployments, it replaces `{name}` with `deployment_name`.

### Environment secrets

- `PGPASSWORD`
- `STITCH_APP_PASSWORD`
- `STITCH_MIGRATOR_PASSWORD`
- `STITCH_CLIENT_PRIVILEGED_BEARER_TOKEN`
- `STITCH_CLIENT_LLM_BEARER_TOKEN`
- `STITCH_LLM_AZURE_OPENAI_API_KEY`
- `AZURE_STATIC_WEB_APPS_DEPLOY_TOKEN`
- `WOODMAC_API_KEY` — WoodMac API key for the `etl` Container App. Required for
  the app to boot (it validates every dataset at startup), so it must be set
  even though GEM does not use it. Only needed on `staging` / `dress-rehearsal`.
- `GHCR_ETL_PULL_TOKEN` — classic PAT with `read:packages` used to pull the ETL
  image from the `stitch-etl-poc` GHCR. Only needed on `staging` /
  `dress-rehearsal`.

Current validation behavior:

- database deploy validates `PGPASSWORD`
- `lane-config-validate` validates:
  - `FRONTEND_PRODUCTION_URL`
  - `FRONTEND_PREVIEW_URL_TEMPLATE`
  - `AUTH_DISABLED`
  - `AUTH_ISSUER`
  - `AUTH_AUDIENCE`
  - `AUTH_JWKS_URI`
  - `AUTH0_DOMAIN`
  - `AUTH0_CLIENT_ID`
  - `AUTH0_AUDIENCE`
  - `STITCH_APP_PASSWORD`
  - `STITCH_CLIENT_PRIVILEGED_BEARER_TOKEN`
  - `STITCH_CLIENT_LLM_BEARER_TOKEN`
  - If any of `STITCH_LLM_AZURE_OPENAI_BASE_URL`, `STITCH_LLM_AZURE_OPENAI_MODEL`, or `STITCH_LLM_AZURE_OPENAI_API_KEY` are set, all three must be set
- DB migrations validate `STITCH_MIGRATOR_PASSWORD`
- frontend deploy validates `AZURE_STATIC_WEB_APPS_DEPLOY_TOKEN`
- container deploy validates that, when `registry-server` is set, both
  `registry-username` (variable) and `registry-password` (secret) are present —
  so a missing ETL pull credential fails fast instead of surfacing as an opaque
  registry `UNAUTHORIZED` from `az containerapp up`
