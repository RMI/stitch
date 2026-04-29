# CI/CD Deployments

The CD pipeline is managed by the GitHub workflow `build-and-deploy.yml`.

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

For PR preview environments, all preview databases are on the same shared
Postgres host, and the container apps are all in the same dev ACA
environment.

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

In repo settings, under `Secrets and variables` > `Actions`, add:

### Secrets

* `AZURE_CLIENT_ID`: Client ID for `GHActions-stitch-cicd`
* `AZURE_SUBSCRIPTION_ID`: Subscription for the target Azure resources
* `AZURE_TENANT_ID`: Tenant for `GHActions-stitch-cicd`
* `PGPASSWORD_DEV`: superuser (`postgres`) password for DB
* `STITCH_APP_PASSWORD_DEV`: password that API user will connect to DB
* `STITCH_MIGRATOR_PASSWORD_DEV`: password that migrator user will connect to DB
  for DDL operations
* `AZURE_STATIC_WEB_APPS_DEPLOY_TOKEN`: Token for Azure SWA

### Variables

* `PGHOST_DEV`: Host for postgres server
