# CI/CD Deployments

The CD pipeline is managed by the GitHub workflow `build-and-deploy.yml`.

It uses two explicit workflow concepts:

* `deployment_lane`: deploy class / GitHub Environment name
* `deployment_name`: concrete runtime target name used for DB and app naming

Branch behavior is:

* push to `main` -> `deployment_lane=development`, `deployment_name=main`
* any PR not targeting `production` -> `deployment_lane=development`, `deployment_name=pr-<number>`
* push to `production` -> `deployment_lane=dress-rehearsal`, `deployment_name=production`
* any PR targeting `production` -> `deployment_lane=staging`, branch-derived `deployment_name`

Examples:

* PR #57 into `main` -> `deployment_name=pr-57`
* PR from `next` into `production` -> `deployment_name=next`
* PR from `hotfix/fix-auth` into `production` -> `deployment_name=hotfix-fix-auth`

It builds Docker images for:

* `api` (also used for DB migration)
* `entity-linkage`
* `stitch-llm`
* `seed`

It then handles deployments for:

* the database, assuming an existing Azure PostgreSQL flexible server
* the API Container App, assuming an existing Container Apps environment
* the entity-linkage Container App in the same environment
* the stitch-llm Container App in the same environment
* the ETL Container Apps (`etl-gem`, `etl-woodmac`) in the same environment,
  on non-`development` lanes only (see below)

### ETL pipelines (temporary POC wiring)

The `etl-gem` and `etl-woodmac` Container Apps are deployed from pre-built images
published by the separate `stitch-etl-poc` repository
(`ghcr.io/rmi/stitch-etl-poc-etl-{gem,woodmac}`). This pipeline does **not** build
them; it only deploys the tag named by the `ETL_GEM_IMAGE_TAG` /
`ETL_WOODMAC_IMAGE_TAG` variables (defaulting to `pr-9`).

Seed and ETL are mutually exclusive per lane:

* `development`: `seed` builds and runs; ETL deploys are skipped.
* `staging` / `dress-rehearsal`: ETL deploys run; `seed` is skipped.

Because the ETL images live in another repo's GHCR, the Container App needs
stored pull credentials. The ephemeral `GITHUB_TOKEN` cannot be used (it expires
and the app re-pulls on every restart), so a long-lived classic PAT with
`read:packages` is required — GHCR does not support fine-grained tokens. These
are supplied to `deploy-container.yml` via the `registry-server` /
`registry-username` inputs and the `registry-password` secret. The frontend
receives each ETL Container App URL (empty when not deployed) and renders the ETL
control page.

CORS: each ETL app allows exactly one browser origin, set at deploy time via
`ETL_GEM_FRONTEND_ORIGIN_URL` / `ETL_WOODMAC_FRONTEND_ORIGIN_URL` (sourced from
the lane's computed `frontend-origin-url`). Unset, they default to
`http://localhost:3000`, so a missing value shows up as a browser CORS
("No 'Access-Control-Allow-Origin' header") failure, not a server error.

#### ETL durable storage (Azure Files — manual setup, not yet wired)

The ETL apps need persistent storage that the current deploy path does not yet
provide: `etl-gem` reads a read-only reference spreadsheet (`GEM_FILE_DIR`,
`/mnt/data`) and `etl-woodmac` keeps a read-write cache (`WOODMAC_DATA_DIR`,
currently the ephemeral `/tmp/woodmac`, lost on every restart/revision). The plan
is one **SMB Azure Files** share per lane, mounted into both apps (gem read-only,
woodmac read-write). `azure/container-apps-deploy-action@v1` cannot mount volumes,
so wiring this in CI requires graduating the ETL jobs to an `az containerapp
update --yaml` step — tracked separately. The Azure-side prerequisites below are
manual and must exist **before** that CI work lands.

These prerequisites are done in the **Azure Portal** (web UI) — no `az` required.
SMB Azure Files registration and mounting are fully supported in the Portal; only
NFS forces the CLI/YAML route, which is another reason to use SMB. Do this per
lane (`staging`, `dress-rehearsal`), in that lane's resource group and Container
Apps environment. Each lane gets its own storage account / share / environment
storage name — the table tracks the concrete values:

| Lane | Storage account | File share | Env storage (mount) name |
|---|---|---|---|
| `staging` | `stitchstaging` | `etl-staging` | `etl-staging` |
| `dress-rehearsal` | _(tbd)_ | _(tbd)_ | _(tbd)_ |

1. **Create a storage account + file share.** Create a Storage account (Standard
   LRS, StorageV2) or reuse one, then under **File shares** add a share (for
   `staging`: account `stitchstaging`, share `etl-staging`).

2. **Upload the data into the share.** In the share's **Browse** view, create a
   `gem/` folder and upload the GEM reference spreadsheet
   (`Global-Oil-and-Gas-Extraction-Tracker-*.xlsx`); add any woodmac seed files
   similarly. The data is intentionally **not** baked into the image.

3. **Register the share on the Container Apps environment.** Open the Container
   Apps **Environment** → **Settings → Volume mounts → Add** → choose **SMB**, and
   enter the storage account name, account key, share name (`etl-staging` for
   staging), and access mode; name the environment storage to match (`etl-staging`).
   This registration lives on the *environment* and persists across app deploys.
   (Container Apps does not support managed-identity access to Azure Files, so the
   account key is required regardless of Portal vs. CLI.)

   To get the account key: go to the **storage account** → **Security +
   networking → Access keys** → **Show** under `key1` and copy the **Key** value
   (either `key1` or `key2` works). This is the same key recorded as the
   `ETL_STORAGE_ACCOUNT_KEY` secret in step 4. Treat it as a secret — it grants
   full access to the storage account; rotate via the same blade if exposed.

4. **Record the names for the future CI wiring** as environment-scoped GitHub
   config: variables `ETL_STORAGE_NAME` (the env storage name, e.g. `etl-staging`)
   and `ETL_STORAGE_SHARE_NAME` (e.g. `etl-staging`), and — if the YAML deploy
   authenticates with the key rather than the pre-registered env storage — secret
   `ETL_STORAGE_ACCOUNT_KEY`.

The per-app **volume mount** (attaching the registered storage to a container at
a path) can also be added in the Portal by editing the app and creating a new
revision — but **do not rely on that for a stable setup**: our deploys run through
`azure/container-apps-deploy-action@v1` (`az containerapp up`), which re-applies
the container spec and will drop a hand-added mount on the next pipeline run. A
Portal mount is fine for a one-off smoke test; for durability the mount must live
in the deploy path (the YAML step in the follow-up task). Steps 1–3 above are
safe to do in the Portal now because they persist independently of app deploys.

Equivalent CLI, for reference (registration is the key step):

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

The ETL apps must run a **single replica**: they hold job state in memory (the
`/status` endpoint) and run one job at a time, so a second replica would fragment
status responses and (once the share is mounted) create a concurrent writer.

This is **enforced on every deploy**, not as a one-time manual setting. The
`azure/container-apps-deploy-action@v1` step (`az containerapp up`) does not
reliably preserve scale settings, so a value set by hand in the Portal can be
reset on the next pipeline run. Instead, `deploy-container.yml` takes optional
`min-replicas` / `max-replicas` inputs and, when either is set, runs a post-deploy
`az containerapp update --min-replicas … --max-replicas …` to reassert them. The
ETL jobs pass `min-replicas: "1"` and `max-replicas: "1"`, so the pin is
self-healing — no manual Portal step needed, and it survives every redeploy. Other
deploys (api, entity-linkage, stitch-llm) omit these inputs and keep their default
scaling.

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

* `AZURE_CLIENT_ID`: managed identity client ID
* `AZURE_SUBSCRIPTION_ID`: Azure subscription containing the target resources
* `AZURE_TENANT_ID`: tenant for the managed identity

Note that federated identity records for this GitHub repository need to be
added to the managed identity. For the current workflows, the required subjects
are:

* `repo:RMI/stitch:pull_request`
* `repo:RMI/stitch:ref:refs/heads/main`
* `repo:RMI/stitch:ref:refs/heads/production`
* `repo:RMI/stitch:environment:development`
* `repo:RMI/stitch:environment:staging`
* `repo:RMI/stitch:environment:dress-rehearsal`

The branch / PR subjects cover workflows that authenticate outside a GitHub
Environment. The `environment:*` subjects are also required because the
lane-scoped deploy jobs authenticate from GitHub Environments named
`development`, `staging`, and `dress-rehearsal`.

All federated credential fields must match exactly:

* Issuer: `https://token.actions.githubusercontent.com`
* Audience: `api://AzureADTokenExchange`
* Subject: case-sensitive exact match

If Azure starts returning `AADSTS7002138`, recreating the affected federated
credential is usually faster than editing it in place.

Managed identity roles:

* `Reader` on `stitch-dev` (Container Apps Environment)
* `Reader` on `STITCH-DEV-RG` (Resource Group)
* `Container Apps Contributor` on `STITCH-DEV-RG` (Resource Group)

## Setup Notes

In repo settings, under `Secrets and variables` > `Actions`, add Azure identity
secrets, then define lane-scoped variables and secrets in GitHub Environments
named:

* `development`
* `staging`
* `dress-rehearsal`

### Repo-level secrets

* `AZURE_CLIENT_ID`: Client ID for `GHActions-stitch-cicd`
* `AZURE_SUBSCRIPTION_ID`: Subscription for the target Azure resources
* `AZURE_TENANT_ID`: Tenant for `GHActions-stitch-cicd`

### Environment variables

* `AZURE_RESOURCE_GROUP` (example: `STITCH-DEV-RG`)
* `AZURE_CONTAINER_APP_ENVIRONMENT` (example: `stitch-dev`)
* `POSTGRES_HOST` (example: `stitch-dev.postgres.database.azure.com`)
* `POSTGRES_PORT` (example: `5432`)
* `POSTGRES_ADMIN_USER` (example: `postgres`)
* `POSTGRES_SSLMODE` (example: `require`)
* `POSTGRES_DEFAULT_DB` (example: `postgres`)
* `FRONTEND_PRODUCTION_URL` (example: `https://witty-mushroom-017a3dc1e.1.azurestaticapps.net`)
* `FRONTEND_PREVIEW_URL_TEMPLATE` (example: `https://witty-mushroom-017a3dc1e-{name}.westus2.1.azurestaticapps.net`)
* `AUTH_DISABLED` (example: `true` for `development`, `false` for `staging` / `dress-rehearsal`)
* `AUTH_ISSUER` (example: `https://rmi-spd.us.auth0.com/`)
* `AUTH_AUDIENCE` (example: `https://stitch-api.local`)
* `AUTH_JWKS_URI` (example: `https://rmi-spd.us.auth0.com/.well-known/jwks.json`)
* `AUTH0_DOMAIN` (example: `rmi-spd.us.auth0.com`)
* `AUTH0_CLIENT_ID` (example: `<public-client-id>`)
* `AUTH0_AUDIENCE` (example: `https://stitch-api.local`)
* `STITCH_LLM_AZURE_OPENAI_BASE_URL` (example: `https://stitch-foundry-dev.openai.azure.com/openai/v1`)
* `STITCH_LLM_AZURE_OPENAI_MODEL` (example: `gpt-5.1-chat`)
* `STITCH_LLM_AZURE_OPENAI_TIMEOUT_SECONDS` (example: `30`)
* `GHCR_ETL_PULL_USERNAME` (example: `your-github-username`) — registry username
  for pulling the ETL images; not sensitive, so it is a variable. Only needed on
  `staging` / `dress-rehearsal`.
* `ETL_GEM_IMAGE_TAG` (example: `pr-9`) — optional; ETL GEM image tag to deploy,
  defaults to `pr-9`. Only used on `staging` / `dress-rehearsal`.
* `ETL_WOODMAC_IMAGE_TAG` (example: `pr-9`) — optional; ETL WoodMac image tag to
  deploy, defaults to `pr-9`. Only used on `staging` / `dress-rehearsal`.
  * NOTE: `FRONTEND_PREVIEW_URL_TEMPLATE` must contain the literal `{name}` placeholder.
For `dress-rehearsal`, the workflow uses `FRONTEND_PRODUCTION_URL` directly. For pull requests, it replaces `{name}` with the raw PR number so PR #106 resolves to `https://witty-mushroom-017a3dc1e-106.westus2.1.azurestaticapps.net`. For other preview deployments, it replaces `{name}` with `deployment_name`.

### Environment secrets

* `PGPASSWORD`
* `STITCH_APP_PASSWORD`
* `STITCH_MIGRATOR_PASSWORD`
* `STITCH_CLIENT_PRIVILEGED_BEARER_TOKEN`
* `STITCH_CLIENT_LLM_BEARER_TOKEN`
* `STITCH_LLM_AZURE_OPENAI_API_KEY`
* `AZURE_STATIC_WEB_APPS_DEPLOY_TOKEN`
* `WOODMAC_API_KEY` — WoodMac API key for the `etl-woodmac` Container App. Only
  needed on `staging` / `dress-rehearsal`.
* `GHCR_ETL_PULL_TOKEN` — classic PAT with `read:packages` used to pull the ETL
  images from the `stitch-etl-poc` GHCR. Only needed on `staging` /
  `dress-rehearsal`.

Current validation behavior:

* database deploy validates `PGPASSWORD`
* `lane-config-validate` validates:
  * `FRONTEND_PRODUCTION_URL`
  * `FRONTEND_PREVIEW_URL_TEMPLATE`
  * `AUTH_DISABLED`
  * `AUTH_ISSUER`
  * `AUTH_AUDIENCE`
  * `AUTH_JWKS_URI`
  * `AUTH0_DOMAIN`
  * `AUTH0_CLIENT_ID`
  * `AUTH0_AUDIENCE`
  * `STITCH_APP_PASSWORD`
  * `STITCH_CLIENT_PRIVILEGED_BEARER_TOKEN`
  * `STITCH_CLIENT_LLM_BEARER_TOKEN`
  * If any of `STITCH_LLM_AZURE_OPENAI_BASE_URL`, `STITCH_LLM_AZURE_OPENAI_MODEL`, or `STITCH_LLM_AZURE_OPENAI_API_KEY` are set, all three must be set
* DB migrations validate `STITCH_MIGRATOR_PASSWORD`
* frontend deploy validates `AZURE_STATIC_WEB_APPS_DEPLOY_TOKEN`
* container deploy validates that, when `registry-server` is set, both
  `registry-username` (variable) and `registry-password` (secret) are present —
  so a missing ETL pull credential fails fast instead of surfacing as an opaque
  registry `UNAUTHORIZED` from `az containerapp up`
