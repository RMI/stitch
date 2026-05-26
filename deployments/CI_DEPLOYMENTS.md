# CI/CD Deployments

The CD pipeline is managed by the GitHub workflow `build-and-deploy.yml`.

It now uses two explicit workflow concepts:

* `deployment_lane`: deploy class / GitHub Environment name
* `deployment_name`: concrete runtime target name used for DB and app naming

Branch behavior is:

* push to `main` -> `deployment_lane=development`, `deployment_name=main`
* PR to `main` -> `deployment_lane=development`, `deployment_name=pr-<number>`
* push to `production` -> `deployment_lane=dress-rehearsal`, `deployment_name=production`
* PR from `next` to `production` -> `deployment_lane=staging`, `deployment_name=next`
* PR from `hotfix/*` to `production` -> `deployment_lane=staging`, branch-derived `deployment_name`

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

* `AZURE_RESOURCE_GROUP`
* `AZURE_CONTAINER_APP_ENVIRONMENT`
* `POSTGRES_HOST`
* `POSTGRES_PORT`
* `POSTGRES_ADMIN_USER`
* `POSTGRES_SSLMODE`
* `POSTGRES_DEFAULT_DB`
* `FRONTEND_PRODUCTION_URL`
* `FRONTEND_PREVIEW_URL_TEMPLATE`

### Environment secrets

* `PGPASSWORD`
* `STITCH_APP_PASSWORD`
* `STITCH_MIGRATOR_PASSWORD`
* `AZURE_STATIC_WEB_APPS_DEPLOY_TOKEN`
