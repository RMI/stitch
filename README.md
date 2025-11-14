# stitch

Stitch is a platform that integrates diverse oil & gas asset datasets, applies AI-driven enrichment with human review, and delivers curated, trustworthy data.

## Development Database

To quickly spin up a seeded PostgreSQL development database, first copy the example environment file:

```bash
cp .env.example .env
```

and update the ENVVARS in the `.env` file as needed.

Then, run the following command to start the database using Docker Compose:

```bash
docker compose up
```

This will start a PostgreSQL instance and automatically seed it with example data using the included seed script.

- The database will be accessible at localhost:5432.
- Connection details (database name, user, password, host, port) are
  configured via environment variables in a `.env` file.
- An example configuration is provided in `.env.example`. Copy it to `.env`
  and adjust values as needed before starting the containers.
- To inspect the data, connect using any PostgreSQL client.
