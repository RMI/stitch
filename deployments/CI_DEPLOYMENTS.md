# CI/CD Deployments

The CD pipeline is managed by the GitHub workflow `build-and-deploy.yml`.

It uses three explicit workflow concepts, all resolved in
`resolve-deployment-context.yml`:

- `deployment_lane`: deploy class / GitHub Environment name
- `deployment_name`: concrete runtime target name used for DB and app naming
- `always_on`: whether this deployment keeps a warm Container App replica

In Actions expressions these are the workflow's hyphenated outputs —
`needs.resolve-context.outputs.deployment-lane`, `…deployment-name`,
`…always-on`. The snake_case spellings below name the concept, not the key.

Branch behavior is:

- push to `main` -> `deployment_lane=development`, `deployment_name=main`
- any PR not targeting `production` -> `deployment_lane=development`, `deployment_name=pr-<zero-padded number>`
- push to `production` -> `deployment_lane=production`, `deployment_name=production`
- any PR targeting `production` -> `deployment_lane=staging`, branch-derived `deployment_name`
- any PR from a `demo/*` branch -> `deployment_lane=staging`, branch-derived `deployment_name` (regardless of whether it targets `main` or `production`)

Pushes to any other branch fail the pipeline rather than guessing a target.

Staging names carry a readable branch tag plus a 4-character hash of the branch,
truncated so that the name plus the longest Container App suffix (`-api`, `-llm`,
`-etl`) stays under Azure's 32-character limit. Examples:

- PR #57 into `main` -> `deployment_name=pr-0057`
- PR #224 from `next` into `production` -> `deployment_name=pr-0224-next-c6c1`
- PR #7 from `hotfix/fix-auth` into `production` -> `deployment_name=pr-0007-hotfix-fix-aut-3c3d`
- PR #232 from `demo/dedupe` into `main` -> `deployment_name=pr-0232-demo-dedupe-7c63`

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
- `staging` / `production`: ETL deploys; `seed` is skipped.

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
NFS forces CLI/YAML) per lane (`staging`, `production`), in that lane's
resource group and Container Apps environment. Each lane gets its own storage
account / share / environment-storage name:

| Lane              | Storage account | File share            | Env storage name (`ETL_STORAGE_NAME`) |
| ----------------- | --------------- | --------------------- | ------------------------------------- |
| `staging`         | `stitchstaging` | `etl-staging`         | `etl-staging`                         |
| `production`      | _(TODO: confirm)_ | `etl-prod`          | `etl-prod`                            |

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
`az containerapp update` that pins replicas. The `etl` app is unoptimized and
needs more memory, so it passes `cpu: "2.0"` / `memory: "4.0Gi"`.
`entity-linkage` used to as well, but is deliberately unpinned now: it is
I/O-bound waiting on sequential API responses, so the extra CPU bought little
while giving its batch pass 4x the CPU of the API it calls.

On the default **Consumption** workload profile, CPU and memory are not
independent — only fixed pairs are valid, with memory (Gi) = 2× vCPU. So **4.0Gi
is only reachable at 2.0 vCPU**; there is no "low CPU + 4 GiB" option without
moving the environment to a Dedicated workload profile. The inputs must be set
together (the deploy validates one-without-the-other and fails fast).

#### Keeping the production release awake (scale-to-zero policy)

By default a Container App scales to zero (`min-replicas: 0`) when idle, so the
first request after a quiet period pays a cold-start. Only the production
release is currently worth paying to avoid that; everywhere else we accept the
cold start to hold the bill down. `resolve-context` decides this once and
exposes it as the `always-on` output:

| Deployment | `always-on` | Why |
| --- | --- | --- |
| push to `production` | `1` | the production release; must be responsive on first hit |
| push to `main` | *(empty)* | cost |
| `staging` lane PRs (into `production`, or from `demo/*`) | *(empty)* | cost |
| `development` lane PRs | *(empty)* | throwaway preview, one per PR |

The three long-running services — `api`, `entity-linkage`, `stitch-llm` — pass it
straight through:

```yaml
min-replicas: ${{ needs.resolve-context.outputs.always-on }}
```

`1` means one warm replica with `max` left at the default, so they still scale
out under load. Empty means the input is skipped entirely and the app keeps the
default scale-to-zero. The ETL app is separate: it pins `min = max = 1` and only
deploys on non-`development` lanes, so it stays warm regardless of this policy.

Apps that do scale to zero also get a widened **cooldown** — 900s rather than
Azure's default 300s — reasserted after every deploy. Cooldown is how long an app
stays up after its last request, so this covers the ordinary gaps inside a
working session without keeping anything alive overnight. There is no CLI flag
for it, so the deploy sets it with the same `show -> jq -> update --yaml`
round-trip used for volume mounts. Always-on apps skip the step; an app that
never scales to zero has no use for a cooldown.

Cooldown only helps when requests cluster closer together than the cooldown
itself, so be sceptical of raising it further without measuring. Sampled over a
13-day window, `main-api` was running for roughly one hour in twenty, and the
gaps between bursts of use were 40, 110, 120 and 220 minutes — none of which
900s bridges. Worth re-measuring once a lane is in real daily use:

```bash
az monitor metrics list --resource "$(az containerapp show -n main-api -g STITCH-DEV-RG --query id -o tsv)" --metric Replicas --interval PT1H --offset 13d --aggregation Maximum -o table
```

Cold starts are most visible at sign-in, when the app's first API call lands on
a sleeping container. The frontend absorbs that, so the policy above does not
have to widen to cover it:

- it wakes the API during bootstrap, before Auth0 mounts, so the container starts
  while the user is still being redirected through login;
- queries retry transient failures, so a container that is not ready yet reads as
  slow rather than broken;
- the environment banner says the server is waking up once a request has been in
  flight for more than a couple of seconds.

entity-linkage and stitch-llm are deliberately left out. Waking them the same way
was tried and set aside: the API is the one every session needs, and better
options for the other two are still being explored.

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

   Do this in `staging` (its `deployment-name`) and for `production`.

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

### Custom domains (RMI hostnames)

There is one Static Web App per lane group, and each has its own production
branch. `deploy-frontend` passes that branch to the Azure deploy action as
`production-branch`, which is what decides whether a deployment lands in the
site's **production** environment or in a **preview** environment.

| Hostname | Status | Lane | Branch | Static Web App | Default hostname |
| --- | --- | --- | --- | --- | --- |
| `stitch-dev.rmi.org` | assigning now | `development` | `main` | `stitch-dev` | `witty-mushroom-017a3dc1e.1.azurestaticapps.net` |
| `stitch.rmi.org` | planned | `production` | `production` | `stitch-prod` | `salmon-bush-05721e11e.6.azurestaticapps.net` |

`stitch.rmi.org` is deliberately **not** pointed at the existing `stitch-staging`
Static Web App. That resource serves the `staging` lane (PR previews into
`production`), not production; the production hostname points at the dedicated
production Static Web App instead, so the name never has to move between
resources. (Moving a bound domain between two Static Web Apps in the same
slice requires downtime — see "Migrating domains between instances" in the Azure
docs.)

**Preview environments cannot have custom domains.** This is an Azure product
limitation, not a configuration gap, so every PR preview stays on an
`azurestaticapps.net` hostname. Giving per-PR previews RMI hostnames would need
Azure Front Door in front of the Static Web Apps, or one Static Web App per lane.
It also means a lane can only get a hostname once its branch deploys to the
site's production environment — which is why `main` uses `main` as its
`production-branch` rather than sharing `production`.

#### Who owns DNS

`rmi.org` is registered and hosted at Network Solutions
(`ns49.worldnic.com` / `ns50.worldnic.com`). There is no Azure DNS zone for it,
so record changes are **not self-service** — they go through RMI IT. A wildcard
`*.rmi.org` record exists, so an unconfigured subdomain will still resolve; a
specific record takes precedence over it.

#### Adding a hostname

1. **Ask IT for a CNAME** from the hostname to the Static Web App's default
   hostname (the table above, or the site's Overview blade in the portal). Check
   first that nothing is already served there — the wildcard makes every name
   resolve, so `dig` alone does not tell you whether the name is in use.
2. **Bind it in Azure.** This part does not need IT; the Stitch team has access
   to the `RMI-PROJECT-STITCH-SUB` subscription. On the Static Web App:
   **Custom domains → Add → Custom domain on other DNS**, hostname record type
   **CNAME**. Azure validates the record, then issues and auto-renews a free
   managed certificate. Validation can take a while to see a fresh record.
3. **Set it as the default domain.** With the domain selected, choose
   **Set default**. Azure then 301-redirects the site's other hostnames —
   including the `azurestaticapps.net` one — to it, so old links keep working.
   Verify an open PR's preview URL still loads after doing this.
4. **Register it with Auth0** on lanes that run `AUTH_DISABLED=false`. Add the
   origin to Allowed Callback URLs, Allowed Logout URLs, and Allowed Web Origins
   in the `rmi-spd` tenant. No code change is needed — the SPA derives its
   `redirect_uri` from `window.location.origin`.
5. **Point the lane at it** by setting `FRONTEND_PRODUCTION_URL` on the lane's
   GitHub Environment to the new origin. This is the actual cutover: it becomes
   the single CORS origin the backend services accept on the next deploy, so do
   it only once the certificate is valid. Update the links in the top-level
   `README.md` at the same time.

#### Troubleshooting: CORS errors after a new hostname goes live

Symptom — the frontend loads at the new custom domain, but API calls fail in the
browser console with:

> `No 'Access-Control-Allow-Origin' header is present on the requested resource`

This means the browser's `Origin` (the custom domain) does not match the single
origin the backend allows. Because each backend service accepts exactly one CORS
origin (the API's `FRONTEND_ORIGIN_URL`, fed from the lane's
`FRONTEND_PRODUCTION_URL`), it happens when the cutover above is only half-done —
typically step 5 (`FRONTEND_PRODUCTION_URL` is still the old `azurestaticapps.net`
hostname) and/or step 3 (the custom domain is not set as default, so the old
hostname still serves the app directly instead of redirecting to it).

Confirm which origin the backend currently allows with a preflight request:

```bash
curl -i -X OPTIONS '<api-origin>/api/v1/health' \
  -H 'Origin: https://<custom-domain>' \
  -H 'Access-Control-Request-Method: GET'
```

A working origin returns `200` with `access-control-allow-origin: <custom-domain>`;
a blocked one returns no `access-control-allow-origin` header. Resolve by
completing step 3 (**Set default**, so the old hostname 301-redirects and stops
originating requests) and step 5 (`FRONTEND_PRODUCTION_URL = https://<custom-domain>`),
then redeploy the lane so the backend containers pick up the new origin.

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
- `repo:RMI/stitch:environment:production`

The branch / PR subjects cover workflows that authenticate outside a GitHub
Environment. The `environment:*` subjects are also required because the
lane-scoped deploy jobs authenticate from GitHub Environments named
`development`, `staging`, and `production`.

> **Reminder — when adding a new lane / GitHub Environment:** creating the
> Environment and populating its variables/secrets is not enough. You must also
> add a matching `repo:RMI/stitch:environment:<lane>` federated-credential subject
> to the `GHActions-stitch-cicd` managed identity, or every deploy job in that
> lane fails at `azure/login` with an OIDC error. (This was the final wiring step
> when the `production` lane replaced `dress-rehearsal`.)

All federated credential fields must match exactly:

- Issuer: `https://token.actions.githubusercontent.com`
- Audience: `api://AzureADTokenExchange`
- Subject: case-sensitive exact match

If Azure starts returning `AADSTS7002138`, recreating the affected federated
credential is usually faster than editing it in place.

Managed identity roles (grant per lane, on that lane's resource group and
Container Apps environment):

- `Reader` on `stitch-dev` (Container Apps Environment)
- `Reader` on `STITCH-DEV-RG` (Resource Group)
- `Container Apps Contributor` on `STITCH-DEV-RG` (Resource Group)
- `Reader` on `stitch-prod` (Container Apps Environment)
- `Reader` on `STITCH-PROD-RG` (Resource Group)
- `Container Apps Contributor` on `STITCH-PROD-RG` (Resource Group)

> **Reminder — when adding a new lane:** the federated-credential subject above
> only lets the identity authenticate; it still needs these role assignments on
> the new lane's resource group and Container Apps environment, or deploys fail
> with authorization errors even though login succeeds. Grant the same
> `Reader` + `Container Apps Contributor` set that the other lanes have.

## Setup Notes

In repo settings, under `Secrets and variables` > `Actions`, add Azure identity
secrets, then define lane-scoped variables and secrets in GitHub Environments
named:

- `development`
- `staging`
- `production`

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
- `FRONTEND_PRODUCTION_URL` — the origin the lane's Static Web App production
  environment is reached at, custom domain included once one is bound
  (example: `https://stitch-dev.rmi.org`). See "Custom domains" below.
- `FRONTEND_PREVIEW_URL_TEMPLATE` (example: `https://witty-mushroom-017a3dc1e-{name}.westus2.1.azurestaticapps.net`)
- `AUTH_DISABLED` (example: `true` for `development`, `false` for `staging` / `production`)
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
  `staging` / `production`.
- `ETL_STORAGE_NAME` (example: `etl-staging`) — the Azure Files env-storage name
  registered on the Container Apps environment; mounted into the `etl` app at
  `/mnt/data`. Only needed on `staging` / `production` (see ETL durable
  storage above).
- `ETL_IMAGE_TAG` (example: `main`) — optional; consolidated ETL image tag to
  deploy, defaults to `main`. Only used on `staging` / `production`.

The two frontend URLs together define the single CORS origin the API,
entity-linkage, and stitch-llm services will accept for a given deployment, so
they have to match where the frontend actually lands:

- A **pull request** always deploys to a Static Web App preview environment named
  for the PR number, so the workflow substitutes the raw PR number into
  `FRONTEND_PREVIEW_URL_TEMPLATE` — PR #106 resolves to
  `https://witty-mushroom-017a3dc1e-106.westus2.1.azurestaticapps.net`. The
  template must contain the literal `{name}` placeholder.
- Any **other event** is a push to a lane's production branch, which deploys to
  that lane's Static Web App production environment, so the workflow uses
  `FRONTEND_PRODUCTION_URL` verbatim.

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
  even though GEM does not use it. Only needed on `staging` / `production`.
- `GHCR_ETL_PULL_TOKEN` — classic PAT with `read:packages` used to pull the ETL
  image from the `stitch-etl-poc` GHCR. Only needed on `staging` /
  `production`.

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
