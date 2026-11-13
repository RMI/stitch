# Database Deployment Details

This directory contains resources for building and running the development PostgreSQL database used by Stitch.

## Overview

- `seed_db.py` : Seeds the database with example data on container startup.
- `volumes`: Used for persistent storage of database data.

## Seeding Process

- On first startup, the container runs `seed_db.py` to populate the database.
- Seeding only occurs if the database is empty (to avoid overwriting existing data).
- The seed script can be modified to change the initial dataset.

## Docker Volumes

- The database data is stored in a Docker volume (`stitch-db-data` by default).
- This ensures data persists across container restarts.
- To reset the database (remove all data and reseed):

  ```bash
  docker compose down -v
  docker compose up
  ```

  This deletes the volume and triggers reseeding.

- Connection details (database name, user, password, host, port) are set via environment variables.
- See `env.example` in the project root for sample configuration.

## Deployment

### Prerequisites

- Azure access to create PostgreSQL Flexible Server
- `psql` tools installed locally
- Docker available (for API connectivity testing)
- Secure location for storing generated passwords (LastPass)

---

### Canonical Deployment Values (Example)

```
SUBSCRIPTION=RMI-PROJECT-STITCH_SUB
RESOURCE_GROUP=STITCH-DEV-RG
REGION=West US 2
POSTGRES_VERSION=17
SERVER_NAME=stitch-deploy-test
DB_NAME=stitch
```

---

### Manual Provisioning (Azure Portal)

Create resource: Azure Database for PostgreSQL Flexible Server

#### Basics

- Subscription: `RMI-PROJECT-STITCH_SUB`
- Resource Group: `STITCH-DEV-RG`
- Region: `West US 2`
- PostgreSQL version: `17`
- Workload Type: Dev/Test
- Compute: Burstable / Standard_B1ms
  - Cluster options: `Server`
  - Compute tier: `Burstable`
  - Compute size: `Standard_B1ms`
  - Storage type: `Premium SSD`
  - Storage size: `32 GiB`
  - Performance tier: `P4 (120 iops)`
  - Storage autogrow: Unchecked
  - Zonal resiliency: Disabled
  - Backup retention period: `7 Days`
  - Geo-redundancy: Unchecked
- Zonal resiliency: Disabled
- Authentication: PostgreSQL and Microsoft Entra Authentication

Set:

- Admin login: `postgres`
- Password: Store securely

#### Networking

- Connectivity: Public access
- Allow Azure services
- Add current client IP
  - Consider renaming new rule to something like `<MY_NAME>_IPAddress_2026-1-22_13-26-17`
- Do NOT allow 0.0.0.0/0 ("0.0.0.0 - 255.255.255.255")
- No private endpoints

---

### Post-Deployment Steps

#### Create Database

Portal → Databases

Create database named:

```
<database_name>
```

#### Verify Connectivity

```bash
pg_isready -d <database_name> -U postgres -h <POSTGRES_HOST>
psql -d <database_name> -U postgres -h <POSTGRES_HOST>
```

If connection fails, verify firewall rules.

---

#### Initialize Roles

```bash
POSTGRES_DB=<database_name> \
    POSTGRES_USER=postgres \
    PGHOST=<POSTGRES_HOST> \
    STITCH_MIGRATOR_PASSWORD=CHANGE_ME123! \
    STITCH_APP_PASSWORD=CHANGE_ME456! \
    deployments/db/00-init-roles.sh
```

Verify:

```bash
psql -d <database_name> -U stitch_migrator -h <POSTGRES_HOST>
psql -d <database_name> -U stitch_app -h <POSTGRES_HOST>
```

---

### Seed Schema and Data

```bash
docker run \
  -e LOG_LEVEL='info' \
  -e POSTGRES_HOST=<POSTGRES_HOST> \
  -e POSTGRES_PORT='5432' \
  -e POSTGRES_USER='stitch_migrator' \
  -e POSTGRES_PASSWORD='CHANGE_ME123!' \
  -e POSTGRES_DB=<database_name> \
  --rm \
  stitch-api:latest alembic -c deployments/api/alembic.ini upgrade head
```

Re-run API container.
You should now see seeded dev data.

---

## Backups

A scheduled Azure Container Apps job backs up one database. The job runs
`pg_dump -Fc` daily at 03:00 UTC. Then it uploads the dump to the `backups`
blob container as `<database>/<timestamp>.dump`.

Each database needs its own job. The job name defaults to the database name
with underscores replaced by hyphens. Use `-n` to choose a different name.

A run stops after 30 minutes. A failed run does not retry. Nothing deletes old
dumps. A lifecycle policy on the `backups` container limits its size.

> [!NOTE] ACA Emphemeral Storage
> Each job uses ephemeral storage to temporarily house the dump before
> uploading to the blob storage account. This scales with the configured
> vCPU count to a maximum of 8Gb. As of 2026-10-21, job containers are
> configured to 0.5 vCPUs, providing 2Gb of storage. Current DB size is
> 50-200Mb depending on instance.

### Deploying the job

`scripts/db_backup_job.sh` needs `az` and `jq`. Before you run the script,
authenticate `az` against the correct subscription.

1. Run `setup` one time for each storage account:

   ```bash
   scripts/db_backup_job.sh setup -g <resource-group> -s <storage-account>
   ```

   This creates the `stitch-backup-identity` managed identity and the `backups`
   container. Then it grants **Storage Blob Data Contributor** to that identity
   on the container.

2. Run `deploy` one time for each database:

   ```bash
   scripts/db_backup_job.sh deploy \
     -g <resource-group> -s <storage-account> -e <environment> \
     -S <server> -d <database> -P <password>
   ```

   Give `-S` the name of the Postgres flexible server, such as
   `stitch-staging`. The script finds the host name for you.

   This creates the job, or updates it when the job exists. Leave off `-P` to
   take the password from `PGPASSWORD` instead.

Every command is safe to run again. For all options, run
`scripts/db_backup_job.sh --help`.

To run `setup`, your account needs these permissions:

- create a managed identity
- create a role assignment
- create a blob container on the storage account

`deploy` only requires read access on the Postgres server.

CAUTION: Wait two minutes after `setup` before you start the job. Azure needs
time to apply the role assignment. Until then, the upload step fails.

### Backing up now

To back up a database immediately, run:

```bash
scripts/db_backup_job.sh run -g <resource-group> -d <database>
```

This starts the same job that `deploy` created, so the dump goes to the same
place. The nightly schedule stays in place. Use this to test a new job, or to
take a dump before a risky change.

The command prints the name of the run it started. To see the result:

```bash
az containerapp job execution list -g <resource-group> -n <job> -o table
```

### Deleting a job

Deleting a database does not delete its job. To delete a job, run:

```bash
scripts/db_backup_job.sh delete -g <resource-group> -d <database>
```

This leaves the identity, the `backups` container, and the dumps in place. It
does nothing when the job is already gone.

---

## Restoring from a backup

`scripts/db_restore.sh` restores one backup into an empty database. Staging
deployments and `make db-restore` both use it. It needs `az`, logged in with
read access to the backups container, and `docker`.

The restore runs as `stitch_migrator`, so `stitch_migrator` owns every restored
object and `stitch_app` gets the same access it has after a migration. The
restore runs in one transaction: it either finishes or changes nothing.

A restored database holds production data, including restricted sources, and the
contents of the `users` table. How to handle those fields is not decided yet
(STIT-48), but not immediately concerning, since staging environments use the
same Auth0 subscription and application as production.

### Staging deployments

When a staging deployment (a PR into `production`, or a PR from a `demo/*`
branch) finds its database empty, as it is when first created, it restores the
newest production backup into it. Alembic then applies only the PR's new
migrations. Later pushes keep the database as it is. The PR summary comment
shows which backup was restored.

To restore a newer backup, add the `no-deploy` label to the PR, then remove it.
This deletes the deployment, and the next deploy restores again. Closing and
reopening the PR does the same.

To restore a specific backup, set `backup-url` on the `deploy-db` job in
`.github/workflows/build-and-deploy.yml` to its full URL, for example
`https://rmistitchprod.blob.core.windows.net/backups/production/20261023T030039Z.dump`.
Use the plain URL, without a SAS token (`?sv=...`): the job log and the PR
comment show it, and the restore signs in as its own identity anyway, so the
script refuses URLs with a query string.
This means editing the GH workflow file, so it's expected to be used rarely, and
for code versions that aren't expected to be merged directly to `main`.

If a restore fails or the run is cancelled, the database stays empty, so the
next push tries again.

#### One-time setup

Staging signs in as the `stitch-restore-identity` managed identity. It can only
read the backups containers, and only workflows in the `staging` GitHub
environment can sign in as it. Set it up before staging deployments start
restoring, or they fail at "Validate restore config".

```bash
az identity create -g STITCH-DEV-RG -n stitch-restore-identity

principal="$(az identity show -g STITCH-DEV-RG -n stitch-restore-identity \
  --query principalId --output tsv)"
prod_backups="$(az storage container-rm show -g STITCH-PROD-RG \
  --storage-account rmistitchprod -n backups --query id --output tsv)"
staging_backups="$(az storage container-rm show -g STITCH-DEV-RG \
  --storage-account stitchstaging -n backups --query id --output tsv)"

for scope in "$prod_backups" "$staging_backups"; do
  az role assignment create --role "Storage Blob Data Reader" \
    --assignee-object-id "$principal" --assignee-principal-type ServicePrincipal \
    --scope "$scope" --output none
done

az identity federated-credential create -g STITCH-DEV-RG \
  --identity-name stitch-restore-identity --name github-staging \
  --issuer https://token.actions.githubusercontent.com \
  --subject repo:RMI/stitch:environment:staging \
  --audiences api://AzureADTokenExchange

gh variable set RESTORE_AZURE_CLIENT_ID --env staging --repo RMI/stitch \
  --body "$(az identity show -g STITCH-DEV-RG -n stitch-restore-identity \
    --query clientId --output tsv)"
```

To restore from another storage account, grant the identity the same role on
that account's backups container first.

CAUTION: Azure takes a couple of minutes to apply a new role assignment. Until
then, the restore fails to list or download backups.

### Local development

To replace your local database with the newest production backup, run:

```bash
make db-restore
```

To restore a specific backup, pass its full URL:

```bash
make db-restore BACKUP_URL=<backup URL>
```

This needs `az login` with **Storage Blob Data Reader** on the backups
container. It finds the newest backup, or checks that `BACKUP_URL` exists,
before anything else, so without access or with a wrong URL it stops before it
changes anything. Then it stops the `api` and `seed` containers, recreates the
`stitch` database and its grants, restores the backup, and runs alembic to
bring the schema up to your branch.

Keep in mind:

- `make api-dev` and `make frontend-dev` run the seed, which adds sample
  records on top of the restored data.
- If your branch is missing a migration that production already has, alembic
  fails with "Can't locate revision". Update your branch from `main` and run
  `make db-restore` again.
- `make clean` and `make reboot-docker` delete the restored data.

---

## Updating Database

⚠ DBA-ONLY WORKFLOW

This is a manual operational process.
It will eventually be replaced with CI-driven migrations.

### Local Docker Database

Remove docker volume (`make clean-docker`) and re-run `alembic`.

### Shared Cloud Database Strategy

1. Rename existing DB:

```
stitch → stitch_old_YYYYMMDD
```

1. Create new empty `stitch` database.

2. Re-grant privileges to:

- stitch_migrator
- stitch_app

(Do not recreate users.)

1. Update local `.env` to point to cloud host.

2. Run:

```bash
docker compose up alembic
```

This should recreate schema and seed data.

Manual schema diffs are not currently supported.
