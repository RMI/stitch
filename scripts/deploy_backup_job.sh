#!/usr/bin/env bash
set -euo pipefail

IDENTITY_NAME=stitch-backup-identity
BLOB_CONTAINER=backups
ROLE="Storage Blob Data Contributor"

spec_template="$(cd "$(dirname "$0")/.." && pwd)/deployments/db/jobs/backup-job.yaml"
spec=

cleanup() {
  [ -z "$spec" ] || rm -f "$spec"
}
trap cleanup EXIT

error_prefix="Error: "
[ -z "${GITHUB_ACTIONS:-}" ] || error_prefix="::error::"

usage() {
  echo "usage: $(basename "$0") {setup|deploy} {staging|production}" >&2
  exit 2
}

fail() {
  echo "$error_prefix$1" >&2
  exit 1
}

check_lane() {
  case "$1" in
    staging | production) ;;
    *) fail "Unknown lane '$1'. Expected staging or production." ;;
  esac
}

github_name() {
  case "$1" in
    LANE_PGHOST) echo POSTGRES_HOST ;;
    LANE_PGUSER) echo POSTGRES_ADMIN_USER ;;
    LANE_PGPASSWORD) echo "PGPASSWORD (secret)" ;;
    LANE_BACKUP_DATABASES) echo BACKUP_DATABASES ;;
    LANE_STORAGE_ACCOUNT) echo BACKUP_STORAGE_ACCOUNT ;;
    *) echo "$1" ;;
  esac
}

require() {
  local name
  for name in "$@"; do
    [ -n "${!name:-}" ] || fail "Missing required variable $(github_name "$name")"
  done
}

container_scope() {
  local account_id
  account_id="$(az storage account show --name "$LANE_STORAGE_ACCOUNT" --query id --output tsv)"
  echo "$account_id/blobServices/default/containers/$BLOB_CONTAINER"
}

role_count() {
  az role assignment list --scope "$1" --output tsv \
    --query "[?principalId=='$2' && roleDefinitionName=='$ROLE'] | length(@)"
}

setup() {
  local lane="$1" principal scope
  check_lane "$lane"
  require AZURE_RESOURCE_GROUP LANE_STORAGE_ACCOUNT

  echo "Lane $lane: resource group $AZURE_RESOURCE_GROUP, storage account $LANE_STORAGE_ACCOUNT"

  principal="$(az identity create --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$IDENTITY_NAME" --query principalId --output tsv)"
  echo "Identity $IDENTITY_NAME ready in $AZURE_RESOURCE_GROUP"

  az storage container create --account-name "$LANE_STORAGE_ACCOUNT" --auth-mode login \
    --name "$BLOB_CONTAINER" --output none
  echo "Container $BLOB_CONTAINER ready on $LANE_STORAGE_ACCOUNT"

  scope="$(container_scope)"
  if [ "$(role_count "$scope" "$principal")" -eq 0 ]; then
    az role assignment create --role "$ROLE" --assignee-object-id "$principal" \
      --assignee-principal-type ServicePrincipal --scope "$scope" --output none
    echo "Granted $ROLE on $BLOB_CONTAINER; allow a minute for it to take effect"
  else
    echo "Already holds $ROLE on $BLOB_CONTAINER"
  fi
}

deploy() {
  local lane="$1" identity principal scope job_name action
  check_lane "$lane"
  require AZURE_RESOURCE_GROUP AZURE_CONTAINER_APP_ENVIRONMENT LANE_PGHOST \
    LANE_PGUSER LANE_PGPASSWORD LANE_BACKUP_DATABASES LANE_STORAGE_ACCOUNT

  identity="$(az identity list --resource-group "$AZURE_RESOURCE_GROUP" \
    --query "[?name=='$IDENTITY_NAME'] | [0]" --output json |
    jq -r 'if . == null then "" else [.id, .clientId, .principalId] | @tsv end')"
  [ -n "$identity" ] ||
    fail "No managed identity '$IDENTITY_NAME' in '$AZURE_RESOURCE_GROUP'. Run '$(basename "$0") setup $lane' first."
  IFS=$'\t' read -r LANE_BACKUP_IDENTITY_ID LANE_BACKUP_IDENTITY_CLIENT_ID principal <<<"$identity"

  [ "$(az storage container exists --account-name "$LANE_STORAGE_ACCOUNT" --auth-mode login \
    --name "$BLOB_CONTAINER" --query exists --output tsv)" = true ] ||
    fail "No container '$BLOB_CONTAINER' on '$LANE_STORAGE_ACCOUNT'. Run '$(basename "$0") setup $lane' first."

  scope="$(container_scope)"
  [ "$(role_count "$scope" "$principal")" -ne 0 ] ||
    fail "Identity '$IDENTITY_NAME' does not hold $ROLE on '$BLOB_CONTAINER'. Run '$(basename "$0") setup $lane' first."

  LANE_ENVIRONMENT_ID="$(az containerapp env show --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$AZURE_CONTAINER_APP_ENVIRONMENT" --query id --output tsv)"
  [ -n "$LANE_ENVIRONMENT_ID" ] ||
    fail "Could not resolve Container Apps environment '$AZURE_CONTAINER_APP_ENVIRONMENT' in '$AZURE_RESOURCE_GROUP'"
  echo "Environment $AZURE_CONTAINER_APP_ENVIRONMENT resolved; the job inherits its location"

  LANE_BACKUP_ENV="$lane"
  LANE_PGPASSWORD_JSON="$(printf '%s' "$LANE_PGPASSWORD" | jq -Rs .)"
  export LANE_BACKUP_IDENTITY_ID LANE_BACKUP_IDENTITY_CLIENT_ID \
    LANE_ENVIRONMENT_ID LANE_BACKUP_ENV LANE_PGPASSWORD_JSON

  job_name="stitch-backup-$lane"
  spec="$(mktemp)"

  envsubst '${LANE_ENVIRONMENT_ID} ${LANE_PGHOST} ${LANE_PGUSER} ${LANE_BACKUP_ENV} ${LANE_BACKUP_DATABASES} ${LANE_STORAGE_ACCOUNT} ${LANE_PGPASSWORD_JSON} ${LANE_BACKUP_IDENTITY_ID} ${LANE_BACKUP_IDENTITY_CLIENT_ID}' \
    <"$spec_template" \
    >"$spec"

  if [ "$(az containerapp job list --resource-group "$AZURE_RESOURCE_GROUP" \
    --query "[?name=='$job_name'] | length(@)" --output tsv)" -eq 0 ]; then
    action=create
    echo "Creating job $job_name"
  else
    action=update
    echo "Updating existing job $job_name"
  fi

  az containerapp job "$action" --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$job_name" --yaml "$spec" --output none

  az containerapp job show --resource-group "$AZURE_RESOURCE_GROUP" --name "$job_name" \
    --query "properties.configuration.{triggerType:triggerType,cron:scheduleTriggerConfig.cronExpression}" \
    --output table
}

[ "$#" -eq 2 ] || usage

case "$1" in
  setup) setup "$2" ;;
  deploy) deploy "$2" ;;
  *) usage ;;
esac
