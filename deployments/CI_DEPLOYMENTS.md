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

Note that a federated identity record for the GH repository needs to be added to
the MSI

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

* `AZURE_CLIENT_ID`: For Managed Identity
* `AZURE_SUBSCRIPTION_ID`: For Managed Identity
* `AZURE_TENANT_ID`: For Managed Identity
* `PGPASSWORD_DEV`: superuser (`postgres`) password for DB
* `STITCH_APP_PASSWORD_DEV`: password that API user will connect to DB
* `STITCH_MIGRATOR_PASSWORD_DEV`: password that migrator user will connect to DB
  for DDL operations
* `AZURE_STATIC_WEB_APPS_DEPLOY_TOKEN`: Token for Azure SWA

### Variables

* `PGHOST_DEV`: Host for postgres server
