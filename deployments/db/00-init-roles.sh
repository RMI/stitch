#!/bin/sh
set -eu

# This script runs automatically on first database initialization
# via /docker-entrypoint-initdb.d.
#
# It bootstraps two roles:
#   - stitch_migrator: DDL + seed (used by db-init job)
#   - stitch_app:      runtime access only (used by API)
#
# Passwords and DB name are taken from environment variables.
#
# Required env:
#   POSTGRES_DB
#   POSTGRES_USER
#   POSTGRES_PASSWORD (used by the container when starting Postgres)
#   STITCH_MIGRATOR_PASSWORD
#   STITCH_APP_PASSWORD
#
# This script:
#  - checks whether stitch_migrator / stitch_app exist
#  - creates them if missing, using psql -v + :'var' substitution so passwords are safely quoted
#  - applies grants / default privileges

: "${POSTGRES_DB:?POSTGRES_DB must be set}"
: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${STITCH_MIGRATOR_PASSWORD:?STITCH_MIGRATOR_PASSWORD must be set}"
: "${STITCH_APP_PASSWORD:?STITCH_APP_PASSWORD must be set}"

escape_sql_literal() {
  # Replace each single quote ' with two single quotes '' (Postgres escaping)
  printf '%s' "$1" | sed "s/'/''/g"
}

# 1) create stitch_migrator
if [ -z "$(
  psql -tA -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -c "SELECT 1 FROM pg_roles WHERE rolname='stitch_migrator'"
)" ]; then
  MIG_ESCAPED=$(escape_sql_literal "$STITCH_MIGRATOR_PASSWORD")
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -c "CREATE ROLE stitch_migrator LOGIN PASSWORD '$MIG_ESCAPED';"
else
  echo "stitch_migrator already exists"
  exit 1
fi

# 2) create stitch_app
if [ -z "$(
  psql -tA -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -c "SELECT 1 FROM pg_roles WHERE rolname='stitch_app'"
)" ]; then
  APP_ESCAPED=$(escape_sql_literal "$STITCH_APP_PASSWORD")
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -c "CREATE ROLE stitch_app LOGIN PASSWORD '$APP_ESCAPED';"
else
  echo "stitch_app already exists"
  exit 1
fi

# 3) Grants: connect to DB (DB name is an identifier; we can use double-quoting safely via shell)
# Note: we avoid psql variable substitution for identifier here to keep things simple.
# If your DB name contains weird characters, you can use psql -v dbname="$POSTGRES_DB" -c 'GRANT CONNECT ON DATABASE :"dbname" TO ...'
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "GRANT CONNECT ON DATABASE \"$POSTGRES_DB\" TO stitch_migrator;"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "GRANT CONNECT ON DATABASE \"$POSTGRES_DB\" TO stitch_app;"

# Schema-level grants (public schema)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "GRANT USAGE ON SCHEMA public TO stitch_migrator;"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "GRANT USAGE ON SCHEMA public TO stitch_app;"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "GRANT CREATE ON SCHEMA public TO stitch_migrator;"

# Default privileges so that objects created BY stitch_migrator are usable by stitch_app
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "ALTER DEFAULT PRIVILEGES FOR ROLE stitch_migrator IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO stitch_app;"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "ALTER DEFAULT PRIVILEGES FOR ROLE stitch_migrator IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO stitch_app;"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "ALTER DEFAULT PRIVILEGES FOR ROLE stitch_migrator IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO stitch_app;"

# Apply privileges to existing objects (defensive)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO stitch_app;"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO stitch_app;"

# Restrict default public schema creation
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "REVOKE CREATE ON SCHEMA public FROM PUBLIC;"
