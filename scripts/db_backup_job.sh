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

usage() {
  cat >&2 <<'EOF'
usage:
  deploy_backup_job.sh setup  -g RG -s ACCOUNT
  deploy_backup_job.sh deploy -g RG -s ACCOUNT -e ENV -H HOST -d DB [-u USER] [-n JOB]
  deploy_backup_job.sh run    -g RG {-d DB | -n JOB}
  deploy_backup_job.sh delete -g RG {-d DB | -n JOB}

options:
  -g, --resource-group   Azure resource group
  -s, --storage-account  storage account holding the backups container
  -e, --environment      Container Apps environment that runs the job
  -H, --host             Postgres host
  -d, --database         database to back up
  -u, --user             Postgres user (default: postgres)
  -n, --name             job name (default: the database name, hyphenated)
  -h, --help             show this message

setup: create & configure identity and permissions for one storage account.

deploy: create/update a job for one database.

run: back up one database immediately by running an existing job.
(All job configuration is left unchanged)

delete: remove the job for one database (does nothing when there's no matching job).
The identity, container, storage account, and any existing dumps remain.

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

job_exists() {
  az containerapp job show --resource-group "$resource_group" --name "$name" \
    --output none 2>/dev/null
}

render() {
  local out pair key value

  out="$(<"$SPEC")"
  for pair in "$@"; do
    key="${pair%%=*}"
    value="${pair#*=}"
    out="${out//\{\{ $key \}\}/$value}"
  done

  case "$out" in
  *'{{'*)
    echo "render: $SPEC has a placeholder with no value" >&2
    return 1
    ;;
  esac

  printf '%s\n' "$out"
}

deploy() {
  local action identity identity_id client_id environment_id pgpassword_json
  : "${PGPASSWORD:?the password for --user on --host}"

  identity="$(az identity show --resource-group "$resource_group" \
    --name "$IDENTITY_NAME" --query "{id: id, clientId: clientId}" --output json)"
  identity_id="$(jq -r .id <<<"$identity")"
  client_id="$(jq -r .clientId <<<"$identity")"
  environment_id="$(az containerapp env show --resource-group "$resource_group" \
    --name "$environment" --query id --output tsv)"
  pgpassword_json="$(printf '%s' "$PGPASSWORD" | jq -Rs .)"

  rendered="$(mktemp)"
  trap 'rm -f "$rendered"' EXIT
  render \
    "identity_id=$identity_id" \
    "identity_client_id=$client_id" \
    "environment_id=$environment_id" \
    "pgpassword_json=$pgpassword_json" \
    "pghost=$host" \
    "pguser=$user" \
    "database=$database" \
    "storage_account=$storage_account" \
    "blob_container=$BLOB_CONTAINER" >"$rendered"

  if job_exists; then
    action=update
  else
    action=create
  fi

  az containerapp job "$action" --resource-group "$resource_group" --name "$name" \
    --yaml "$rendered" --output none

  echo "Job $name backs up $database nightly to $storage_account/$BLOB_CONTAINER/$database"
}

run() {
  local execution

  [ -n "$name" ] || usage

  execution="$(az containerapp job start --resource-group "$resource_group" \
    --name "$name" --query name --output tsv)"

  echo "Started $execution. Check on it with:"
  echo "  az containerapp job execution list -g $resource_group -n $name -o table"
}

delete() {
  [ -n "$name" ] || usage

  if ! job_exists; then
    echo "No job named $name in $resource_group"
    return
  fi

  az containerapp job delete --resource-group "$resource_group" --name "$name" \
    --yes --output none

  echo "Deleted job $name. Its dumps in $BLOB_CONTAINER are untouched."
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

[ -n "$name" ] || name="${database//_/-}"

case "$command" in
setup) setup ;;
deploy) deploy ;;
run) run ;;
delete) delete ;;
*) usage ;;
esac
