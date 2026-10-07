#!/usr/bin/env bash
# Dump each database in BACKUP_DATABASES and upload it to the backups container.
#
# Each database is dumped, uploaded and deleted before the next one starts, so
# local disk only ever holds one dump. A failure on one database does not stop
# the others; the script exits non-zero at the end if any database failed, so a
# partial backup still shows up as a failed job execution.
#
# Blobs are named <BACKUP_ENV>/<BACKUP_KIND>/<database>/<timestamp>.dump, with the
# kind before the database so a lifecycle rule can target one kind by prefix.
#
# Expected environment:
#   BACKUP_DATABASES      space-separated database names
#   BACKUP_ENV            lane the databases belong to (e.g. production)
#   BACKUP_KIND           what triggered the backup (e.g. nightly, pre-migration)
#   BACKUP_STORAGE_ACCOUNT  storage account that holds the backups container
#   PGHOST, PGUSER, PGPASSWORD (and optionally PGSSLMODE)  libpq connection settings
#   AZCOPY_AUTO_LOGIN_TYPE=MSI and AZCOPY_MSI_CLIENT_ID  azcopy managed identity sign-in
set -uo pipefail

: "${BACKUP_DATABASES:?Missing BACKUP_DATABASES}"
: "${BACKUP_ENV:?Missing BACKUP_ENV}"
: "${BACKUP_KIND:?Missing BACKUP_KIND}"
: "${BACKUP_STORAGE_ACCOUNT:?Missing BACKUP_STORAGE_ACCOUNT}"

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
export AZCOPY_LOG_LOCATION="$scratch/azcopy-logs"
export AZCOPY_JOB_PLAN_LOCATION="$scratch/azcopy-plans"

container_url="https://${BACKUP_STORAGE_ACCOUNT}.blob.core.windows.net/backups"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
failed=0

for db in $BACKUP_DATABASES; do
  dump="$scratch/$db.dump"

  if ! pg_dump -Fc -d "$db" -f "$dump"; then
    echo "pg_dump failed for $db" >&2
    rm -f "$dump"
    failed=1
    continue
  fi

  if ! azcopy cp "$dump" "$container_url/$BACKUP_ENV/$BACKUP_KIND/$db/$timestamp.dump" --overwrite=false; then
    echo "upload failed for $db" >&2
    failed=1
  fi

  rm -f "$dump"
done

if [ "$failed" -ne 0 ]; then
  echo "Backup finished with errors" >&2
fi
exit "$failed"
