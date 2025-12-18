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

## Environment Variables

- Connection details (database name, user, password, host, port) are set via environment variables.
- See `.env.example` in the project root for sample configuration.

## Manual Seeding

If you need to rerun the seed script manually:

1. Exec into the running container:
   ```bash
   docker exec -it <container_name> bash
   ```
2. Run the seed script:
   ```bash
   python /docker-entrypoint-initdb.d/seed_db.py
   ```

## Troubleshooting

- If the database does not seed as expected, ensure the volume is removed before restarting.
- Check container logs for errors during seeding.
