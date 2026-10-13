#!/usr/bin/env bash
set -euo pipefail

IDENTITY_NAME=stitch-backup-identity
BLOB_CONTAINER=backups
ROLE="Storage Blob Data Contributor"
SPEC="$(cd "$(dirname "$0")" && pwd)/templates/db-backup-job-config.yml"

resource_group=
storage_account=
environment=
host=
database=
user=postgres
name=
rendered=

usage() {
  cat >&2 <<'EOF'
usage:
  deploy_backup_job.sh setup  -g RG -s ACCOUNT
  deploy_backup_job.sh deploy -g RG -s ACCOUNT -e ENV -H HOST -d DB [-u USER] [-n JOB]

options:
  -g, --resource-group   resource group of the identity, storage account and environment
  -s, --storage-account  storage account holding the backups container
  -e, --environment      Container Apps environment that runs the job
  -H, --host             Postgres host
  -d, --database         database to back up
  -u, --user             Postgres user (default: postgres)
  -n, --name             job name (default: the database name, hyphenated)
  -h, --help             show this message

setup prepares one storage account: it creates the backup identity and the
backups container, and lets that identity write there. Run it once per account.

deploy creates or updates the nightly job for a single database, reading the
password from PGPASSWORD. One job backs up one database, so run deploy once per
database you want backed up.
EOF
  exit 2
}

setup() {
  local principal account_id

  principal="$(az identity create --resource-group "$resource_group" \
    --name "$IDENTITY_NAME" --query principalId --output tsv)"

  az storage container create --account-name "$storage_account" --auth-mode login \
    --name "$BLOB_CONTAINER" --output none

  account_id="$(az storage account show --name "$storage_account" --query id --output tsv)"
  az role assignment create --role "$ROLE" --assignee-object-id "$principal" \
    --assignee-principal-type ServicePrincipal \
    --scope "$account_id/blobServices/default/containers/$BLOB_CONTAINER" --output none

  echo "$IDENTITY_NAME can now write to $BLOB_CONTAINER on $storage_account"
}

deploy() {
  local action
  : "${PGPASSWORD:?the password for --user on --host}"
  [ -n "$name" ] || name="${database//_/-}"

  IFS=$'\t' read -r JOB_IDENTITY_ID JOB_IDENTITY_CLIENT_ID < <(
    az identity show --resource-group "$resource_group" --name "$IDENTITY_NAME" \
      --query "[id, clientId]" --output tsv
  )
  JOB_ENVIRONMENT_ID="$(az containerapp env show --resource-group "$resource_group" \
    --name "$environment" --query id --output tsv)"
  JOB_PGPASSWORD_JSON="$(printf '%s' "$PGPASSWORD" | jq -Rs .)"

  export JOB_IDENTITY_ID JOB_IDENTITY_CLIENT_ID JOB_ENVIRONMENT_ID JOB_PGPASSWORD_JSON
  export JOB_PGHOST="$host" JOB_PGUSER="$user" JOB_DATABASE="$database" \
    JOB_STORAGE_ACCOUNT="$storage_account"

  rendered="$(mktemp)"
  trap 'rm -f "$rendered"' EXIT
  envsubst '${JOB_IDENTITY_ID} ${JOB_IDENTITY_CLIENT_ID} ${JOB_ENVIRONMENT_ID}
    ${JOB_PGPASSWORD_JSON} ${JOB_PGHOST} ${JOB_PGUSER} ${JOB_DATABASE}
    ${JOB_STORAGE_ACCOUNT}' <"$SPEC" >"$rendered"

  if az containerapp job show --resource-group "$resource_group" --name "$name" \
    --output none 2>/dev/null; then
    action=update
  else
    action=create
  fi

  az containerapp job "$action" --resource-group "$resource_group" --name "$name" \
    --yaml "$rendered" --output none

  echo "Job $name backs up $database nightly to $storage_account/$BLOB_CONTAINER/$database"
}

command="${1:-}"
shift || usage

while [ "$#" -gt 0 ]; do
  [ "$#" -ge 2 ] || usage
  case "$1" in
    -h | --help) usage ;;
    -g | --resource-group) resource_group="$2" ;;
    -s | --storage-account) storage_account="$2" ;;
    -e | --environment) environment="$2" ;;
    -H | --host) host="$2" ;;
    -d | --database) database="$2" ;;
    -u | --user) user="$2" ;;
    -n | --name) name="$2" ;;
    *) usage ;;
  esac
  shift 2
done

case "$command" in
  setup) setup ;;
  deploy) deploy ;;
  *) usage ;;
esac
