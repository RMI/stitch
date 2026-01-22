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
