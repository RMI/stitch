# stitch

Stitch is a platform that integrates diverse oil & gas asset datasets, applies AI-driven enrichment with human review, and delivers curated, trustworthy data.

## Development Database

To quickly start a seeded PostgreSQL development database:

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
2. Update environment variables in `.env` as needed.
3. Start the database using Docker Compose:
   ```bash
   docker compose up
   ```

This launches PostgreSQL and seeds it with example data.  

With the application up in docker, you can visit `localhost:3000` to visit
