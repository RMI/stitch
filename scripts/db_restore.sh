#!/usr/bin/env bash
set -euo pipefail

DEFAULT_PREFIX=https://rmistitchprod.blob.core.windows.net/backups/production/
PG_IMAGE=postgres:17-alpine
URL_PATTERN='^https://([a-z0-9]+)\.blob\.core\.windows\.net/([a-z0-9-]+)/(.*)$'
BACKUP_NAME_PATTERN='(^|/)[0-9]{8}T[0-9]{6}Z\.dump$'

prefix="$DEFAULT_PREFIX"
backup_url=
database=
user=stitch_migrator

usage() {
  cat >&2 <<'EOF'
usage:
  db_restore.sh latest  [-p PREFIX_URL]
  db_restore.sh restore -d DB [-b BACKUP_URL] [-u USER]

options:
  -p, --prefix      blob URL prefix to search for backups
                    (default: the production backups)
  -b, --backup-url  full blob URL of the backup to restore
                    (default: the newest backup under the default prefix)
  -d, --database    database to restore into
  -u, --user        Postgres user that will own the restored objects
                    (default: stitch_migrator)
  -h, --help        show this message

latest: print the URL of the newest backup under the prefix. Only backups
named the way the backup job names them (<timestamp>.dump) count.

restore: download one backup and restore it into an existing, empty database.
The database must already have the roles and grants from
deployments/db/00-init-roles.sh. Connection settings come from PGHOST,
PGPORT, PGPASSWORD and PGSSLMODE.

Both commands need `az` logged in with read access to the backups container.
restore also needs docker.

EOF
  exit 2
}

latest() {
  local account container path names newest

  if [[ ! "$prefix" =~ $URL_PATTERN ]]; then
    echo "Invalid prefix: '$prefix'. Expected https://<account>.blob.core.windows.net/<container>/<path>" >&2
    exit 1
  fi
  account="${BASH_REMATCH[1]}"
  container="${BASH_REMATCH[2]}"
  path="${BASH_REMATCH[3]}"

  names="$(az storage blob list --auth-mode login \
    --account-name "$account" --container-name "$container" \
    --prefix "$path" --num-results "*" --query "[].name" --output tsv)"

  # The backup job names each dump by its UTC timestamp, so the last one in
  # sort order is the newest. Anything else under the prefix is ignored.
  newest="$(grep -E "$BACKUP_NAME_PATTERN" <<<"$names" | sort | tail -n 1 || true)"

  if [ -z "$newest" ]; then
    echo "No backups named <timestamp>.dump found under $prefix" >&2
    exit 1
  fi

  echo "https://$account.blob.core.windows.net/$container/$newest"
}

restore() {
  [ -n "$database" ] || usage
  [ -n "$backup_url" ] || backup_url="$(latest)"

  if [[ ! "$backup_url" =~ $URL_PATTERN ]] || [ -z "${BASH_REMATCH[3]}" ]; then
    echo "Invalid backup URL: '$backup_url'. Expected https://<account>.blob.core.windows.net/<container>/<blob>" >&2
    exit 1
  fi

  scratch="$(mktemp -d)"
  trap 'rm -rf "$scratch"' EXIT

  echo "Downloading $backup_url"
  az storage blob download --auth-mode login --blob-url "$backup_url" \
    --file "$scratch/dump" --no-progress --output none

  # Use the image the backup job dumps with: an older pg_restore can't read
  # its archives. Restoring without owners or grants leaves every object owned
  # by --user, so the default privileges from 00-init-roles.sh give stitch_app
  # the same access it has after a migration.
  echo "Restoring into $database as $user"
  PGUSER="$user" docker run --rm --interactive \
    --add-host host.docker.internal:host-gateway \
    --env PGHOST --env PGPORT --env PGUSER --env PGPASSWORD --env PGSSLMODE \
    "$PG_IMAGE" \
    pg_restore --dbname "$database" --no-owner --no-acl \
    --single-transaction --exit-on-error <"$scratch/dump"

  echo "Restored $backup_url into $database"
}

command="${1:-}"
shift || usage

while [ "$#" -gt 0 ]; do
  [ "$#" -ge 2 ] || usage
  case "$1" in
  -h | --help) usage ;;
  -p | --prefix) prefix="$2" ;;
  -b | --backup-url) backup_url="$2" ;;
  -d | --database) database="$2" ;;
  -u | --user) user="$2" ;;
  *) usage ;;
  esac
  shift 2
done

case "$command" in
latest) latest ;;
restore) restore ;;
*) usage ;;
esac
