# CI/CD Deployments

The CD pipeline is managed by the github workflow `build-and-deploy.yml`.

It builds:
* the docker images for:
    * `api` (which is also used for DB migration)
    * `entity-linkage,`
    * `seed`, 

It then handles deployments:

* DB (assumes an existing Azure PostgreSQL flexible host)
* API Container app (Assumes an existing Container Apps environment)
* entity-linkage Container app (deploys to same environment)

Note that for PR Preview environments, all preview databases are on the same
shared Postgres Host, and the container apps are all in the same dev ACA
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

Roles for MSI:

Reader
 stitch-dev
Container Apps Environment
GHActions-stitch-cicd

Reader
 STITCH-DEV-RG
Resource Group
GHActions-stitch-cicd

Container Apps Contributor
 STITCH-DEV-RG
Resource Group
GHActions-stitch-cicd

## Setup Notes

Setting up Secrets:

In Repo settings, under "Secrets and variables"/"Actions", add:

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
