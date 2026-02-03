# stitch

Stitch is a platform that integrates diverse oil & gas asset datasets, applies AI-driven enrichment with human review, and delivers curated, trustworthy data.

## Local Development

Local development is run via Docker Compose (DB + API + Frontend) with optional DB initialization/seeding.

### Prerequisites

- Docker Desktop (includes Docker Engine + Docker Compose)

Verify:
```bash
docker --version
docker compose version
```

### Setup

Create your local environment file:
``` bash
cp env.example .env
```

Edit `.env` as needed (passwords, seed settings, etc.).

### Running the Application

Start (and build) the stack:
```bash
docker compose up --build

# or, if you have make installed:
make dev-docker
```

or, if already built:
```bash
docker compose up db api frontend
```

Useful URLs:
- Frontend: http://localhost:3000
- API docs (Swagger): http://localhost:8000/docs
- Adminer (DB UI): http://localhost:8081

Note: The `db-init` service runs automatically (via `depends_on`) to apply schema and seed data based on `.env`:
- `STITCH_DB_SCHEMA_MODE`
- `STITCH_DB_SEED_MODE`
- `STITCH_DB_SEED_PROFILE`

## Reset (wipe DB volumes safely)

Stop containers and delete the Postgres volume (this removes all local DB data):
```bash
docker compose down -v

# or, if you have make installed:
make clean-docker
```

Then start fresh:
```bash
docker compose up db api frontend
```
