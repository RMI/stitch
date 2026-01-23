# Database Deployment Details

This directory contains resources for building and running the development PostgreSQL database used by Stitch.

## Overview

- `Dockerfile`: Builds an image based on `stitch-core`, with the seeding logic.
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

## Deployment

### Manual Process

Create a Resource: "Azure Database for PostgreSQL Flexible Server"

#### Basics

* Subscription: `RMI-PROJECT-STITCH_SUB`
* Resource Group: `STITCH-DB-RG`
* Region: `West US 2`
* PostgreSQL version: `17`
* Workload Type: `Dev/Test`
* Compute + storage: Click "Configure server"
  * Cluster options: `Server`
  * Compute tier: `Burstable`
  * Compute size: `Standard_B1ms`
  * Storage type: `Premium SSD`
  * Storage size: `32 GiB`
  * Performance tier: `P4 (120 iops)`
  * Storage autogrow: Unchecked
  * Zonal resiliency: Disabled
  * Backup retention period: `7 Days`
  * Geo-redundancy: Unchecked
* Zonal resiliency: Disabled
* Authentication: PostgreSQL and Microsoft Entra Authentication
* Microsoft Entra administrator: Click "Set admin"
  * `Admin_Alex@rmi.org`
* Administrator login: `postgres`
* Password: Set password and note elsewhere
* Confirm password

#### Networking

* Connectivity method: `Public access`
* Check "Allow public access to this resource through the internet using a
  public IP address"
* Check "Allow public access from any Azure service within Azure to this server"
* Click "Add current client IP address"
  * Consider renaming new rule to something like `Alex_IPAddress_2026-1-22_13-26-17`
* *DO NOT CLICK* "Add 0.0.0.0 - 255.255.255.255"
* No Private endpoints

#### Security

* Data encryption key: `Service-managed key`

#### Tags

* as appropriate

#### Review and Create

Click Create, then visit your new DB.

#### After Deploy:


##### Create Database

In the Web UI, under "Settings"/"Databases" on the left menu, view the existing
databases.
If the `stitch` database does not exist, create it.

##### Run init Roles init script

test your connection (assuming you have psql tools installed locally):
```bash
pg_isready -d stitch -U postgres -h stitch-deploy-test.postgres.database.azure.com 

psql -c "\\q" -d stitch -U postgres -h stitch-deploy-test.postgres.database.azure.com

```

Change the host above with the "Endpoint" from the resource main view,

If you cannot connect, check that your client IP address is added to the firewall rules under "Settings"/"Networking" on the left menu.

Then run the init script against your new database:
```bash
POSTGRES_DB=stitch \
    POSTGRES_USER=postgres \
    PGHOST=stitch-deploy-test.postgres.database.azure.com \
    STITCH_MIGRATOR_PASSWORD=CHANGE_ME123! \
    STITCH_APP_PASSWORD=CHANGE_ME456! \
    deployments/db/00-init-roles.sh
```

Then check that you can connect as the new roles:

```bash

psql -c "\\q" -d stitch -U stitch_migrator -h stitch-deploy-test.postgres.database.azure.com
psql -c "\\q" -d stitch -U stitch_app -h stitch-deploy-test.postgres.database.azure.com

```

##### Connect with local docker containers

Assuming you have built the docker container for the API locally (with `docker
compose up api --build` or `docker compose build api`), you should have an image
called `stitch-api`, and be able to attempt connecting with that container to
the public DB.

```bash

docker run \
    -e LOG_LEVEL='info' \
    -e POSTGRES_DB='stitch' \
    -e POSTGRES_HOST='stitch-deploy-test.postgres.database.azure.com' \
    -e POSTGRES_PORT='5432' \
    -e POSTGRES_USER='stitch_app' \
    -e POSTGRES_PASSWORD='CHANGE_ME456!' \
    --rm \
    -p 8000:8000 \
    stitch-api:latest

```

If you try to hit the API (i.e. visit `http://localhost:8000/api/v1/resources/2`, then you should get an `500 Internal Server Error`, with a sqlalchemy error along the lines of `realtion "resources" does not exist`.
This confirms that the API container can sucessfully connect to the DB, but the DDL operations and seeding have no been done by the `db-init` container.

You can seed the database by connecting with the migrator role, and running the
init command:

```bash

docker run \
    -e LOG_LEVEL='info' \
    -e POSTGRES_DB='stitch' \
    -e POSTGRES_HOST='stitch-deploy-test.postgres.database.azure.com' \
    -e POSTGRES_PORT='5432' \
    -e POSTGRES_USER='stitch_migrator' \
    -e POSTGRES_PASSWORD='CHANGE_ME123!' \
    --rm \
    -p 8000:8000 \
    stitch-api:latest python -m stitch.api.db.init_job

```

You can then re-connect with the API container (use the command above), and
should be able to see the seeded dev data through the API.
