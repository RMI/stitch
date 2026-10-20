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
`pg_dump -Fc` at 03:00 UTC. Then it uploads the dump to the `backups` blob
container as `<database>/<timestamp>.dump`.

Each database needs its own job. The job name is the database name, with
hyphens in place of underscores. Use `-n` to choose a different name.

A run stops after 30 minutes. A failed run does not retry. Nothing deletes old
dumps. A lifecycle policy on the `backups` container limits its size.

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
     -H <postgres-host> -d <database> -P <password>
   ```

   This creates the job, or updates it when the job exists. Leave off `-P` to
   take the password from `PGPASSWORD` instead.

Every command is safe to run again. For all options, run
`scripts/db_backup_job.sh --help`.

To run `setup`, your account needs these permissions:

- create a managed identity
- create a role assignment
- create a blob container on the storage account

`deploy` needs none of these permissions.

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

2. Create new empty `stitch` database.

3. Re-grant privileges to:

- stitch_migrator
- stitch_app

(Do not recreate users.)

4. Update local `.env` to point to cloud host.

5. Run:

```bash
docker compose up alembic
```

This should recreate schema and seed data.

Manual schema diffs are not currently supported.
