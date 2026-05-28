# CI/CD Deployments

The CD pipeline is managed by the GitHub workflow `build-and-deploy.yml`.

It now uses two explicit workflow concepts:

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

Reusable workflows now select lane-specific configuration from GitHub
Environments and are expected to fail loudly when required values are absent.

The top-level deploy workflow also performs early lane validation before API and
frontend deploys proceed.

Backend infrastructure (static resources like PostgreSQL server or Continer App
environment) are shared within a deploy lane (all `development` lane
deployments, `pr-*`, `main` deploy to the same PostgreSQL instance, with
separate logical DBs)

It also handles running `db-init` (`api` container with different script) and
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
  * NOTE: `FRONTEND_PREVIEW_URL_TEMPLATE` must contain the literal `{name}` placeholder.
For `dress-rehearsal`, the workflow uses `FRONTEND_PRODUCTION_URL` directly. For pull requests, it replaces `{name}` with the raw PR number so PR #106 resolves to `https://witty-mushroom-017a3dc1e-106.westus2.1.azurestaticapps.net`. For other preview deployments, it replaces `{name}` with `deployment_name`.

### Environment secrets

* `PGPASSWORD`
* `STITCH_APP_PASSWORD`
* `STITCH_MIGRATOR_PASSWORD`
* `AZURE_STATIC_WEB_APPS_DEPLOY_TOKEN`

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
* DB init validates `STITCH_MIGRATOR_PASSWORD`
* frontend deploy validates `AZURE_STATIC_WEB_APPS_DEPLOY_TOKEN`
