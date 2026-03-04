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
stitch
```

#### Verify Connectivity

```bash
pg_isready -d stitch -U postgres -h <POSTGRES_HOST>
psql -d stitch -U postgres -h <POSTGRES_HOST>
```

If connection fails, verify firewall rules.

---

#### Initialize Roles

```bash
POSTGRES_DB=stitch \
    POSTGRES_USER=postgres \
    PGHOST=<POSTGRES_HOST> \
    STITCH_MIGRATOR_PASSWORD=CHANGE_ME123! \
    STITCH_APP_PASSWORD=CHANGE_ME456! \
    deployments/db/00-init-roles.sh
```

Verify:

```bash
psql -d stitch -U stitch_migrator -h <POSTGRES_HOST>
psql -d stitch -U stitch_app -h <POSTGRES_HOST>
```

---

### Seed Schema and Data

```bash
docker run \
  -e LOG_LEVEL='info' \
  -e POSTGRES_HOST=<POSTGRES_HOST> \
  -e POSTGRES_USER=stitch_migrator \
  -e POSTGRES_PASSWORD=CHANGE_ME123! \
  -e POSTGRES_PORT='5432' \
  -e POSTGRES_USER='stitch_migrator' \
  -e POSTGRES_PASSWORD='CHANGE_ME123!' \
  --rm \
  stitch-api:latest python -m stitch.api.db.init_job
```

Re-run API container.
You should now see seeded dev data.

---

## Updating Database

⚠ DBA-ONLY WORKFLOW

This is a manual operational process.
It will eventually be replaced with CI-driven migrations.

### Local Docker Database

Remove docker volume (`make clean-docker`) and re-run `db-init`.

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
docker compose up db-init
```

This should recreate schema and seed data.

Manual schema diffs are not currently supported.

