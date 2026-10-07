#!/usr/bin/env bash
set -euo pipefail

IDENTITY_NAME=stitch-backup-identity
BLOB_CONTAINER=backups
ROLE="Storage Blob Data Contributor"

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
spec_template="$repo_root/deployments/db/jobs/backup-job.yaml"

usage() {
  echo "usage: $(basename "$0") {setup|deploy} <lane>" >&2
  exit 2
}

fail() {
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    echo "::error::$1" >&2
  else
    echo "Error: $1" >&2
  fi
  exit 1
}

require() {
  local name
  for name in "$@"; do
    if [ -z "${!name:-}" ]; then
      fail "Missing required variable $name"
    fi
  done
}

container_scope() {
  local account_id
  account_id="$(az storage account show \
    --name "$LANE_STORAGE_ACCOUNT" \
    --query id \
    --output tsv)"
  printf '%s/blobServices/default/containers/%s' "$account_id" "$BLOB_CONTAINER"
}

setup() {
  local lane="$1"
  require AZURE_RESOURCE_GROUP LANE_STORAGE_ACCOUNT

  echo "Preparing backup prerequisites for lane $lane"

  az identity create \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$IDENTITY_NAME" \
    --output none

  local principal
  principal="$(az identity show \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$IDENTITY_NAME" \
    --query principalId \
    --output tsv)"
  echo "Identity $IDENTITY_NAME ready in $AZURE_RESOURCE_GROUP"

  az storage container create \
    --account-name "$LANE_STORAGE_ACCOUNT" \
    --auth-mode login \
    --name "$BLOB_CONTAINER" \
    --output none
  echo "Container $BLOB_CONTAINER ready on $LANE_STORAGE_ACCOUNT"

  local scope granted
  scope="$(container_scope)"
  granted="$(az role assignment list \
    --scope "$scope" \
    --query "[?principalId=='$principal' && roleDefinitionName=='$ROLE'] | length(@)" \
    --output tsv)"
  if [ "$granted" -eq 0 ]; then
    az role assignment create \
      --role "$ROLE" \
      --assignee-object-id "$principal" \
      --assignee-principal-type ServicePrincipal \
      --scope "$scope" \
      --output none
    echo "Granted $ROLE on $BLOB_CONTAINER; allow a minute for it to take effect"
  else
    echo "Already holds $ROLE on $BLOB_CONTAINER"
  fi
}

deploy() {
  local lane="$1"
  require AZURE_RESOURCE_GROUP AZURE_CONTAINER_APP_ENVIRONMENT LANE_PGHOST \
    LANE_PGUSER LANE_PGPASSWORD LANE_BACKUP_DATABASES LANE_STORAGE_ACCOUNT

  if ! LANE_BACKUP_IDENTITY_ID="$(az identity show \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$IDENTITY_NAME" \
    --query id \
    --output tsv 2>/dev/null)"; then
    fail "No managed identity '$IDENTITY_NAME' in '$AZURE_RESOURCE_GROUP'. Run '$(basename "$0") setup $lane' first."
  fi

  LANE_BACKUP_IDENTITY_CLIENT_ID="$(az identity show \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$IDENTITY_NAME" \
    --query clientId \
    --output tsv)"

  LANE_ENVIRONMENT_ID="$(az containerapp env show \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$AZURE_CONTAINER_APP_ENVIRONMENT" \
    --query id \
    --output tsv)"
  if [ -z "$LANE_ENVIRONMENT_ID" ]; then
    fail "Could not resolve Container Apps environment '$AZURE_CONTAINER_APP_ENVIRONMENT' in '$AZURE_RESOURCE_GROUP'"
  fi
  echo "Environment $AZURE_CONTAINER_APP_ENVIRONMENT resolved; the job inherits its location"

  LANE_BACKUP_ENV="$lane"
  LANE_PGPASSWORD_JSON="$(printf '%s' "$LANE_PGPASSWORD" | jq -Rs .)"
  export LANE_BACKUP_IDENTITY_ID LANE_BACKUP_IDENTITY_CLIENT_ID \
    LANE_ENVIRONMENT_ID LANE_BACKUP_ENV LANE_PGPASSWORD_JSON

  local job_name spec
  job_name="stitch-backup-$lane"
  spec="$(mktemp)"
  trap 'rm -f "$spec"' EXIT

  envsubst '${LANE_ENVIRONMENT_ID} ${LANE_PGHOST} ${LANE_PGUSER} ${LANE_BACKUP_ENV} ${LANE_BACKUP_DATABASES} ${LANE_STORAGE_ACCOUNT} ${LANE_PGPASSWORD_JSON} ${LANE_BACKUP_IDENTITY_ID} ${LANE_BACKUP_IDENTITY_CLIENT_ID}' \
    <"$spec_template" \
    >"$spec"

  if az containerapp job show \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$job_name" \
    --output none 2>/dev/null; then
    echo "Updating existing job $job_name"
    az containerapp job update \
      --resource-group "$AZURE_RESOURCE_GROUP" \
      --name "$job_name" \
      --yaml "$spec" \
      --output none
  else
    echo "Creating job $job_name"
    az containerapp job create \
      --resource-group "$AZURE_RESOURCE_GROUP" \
      --name "$job_name" \
      --yaml "$spec" \
      --output none
  fi

  az containerapp job show \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$job_name" \
    --query "properties.configuration.{triggerType:triggerType,cron:scheduleTriggerConfig.cronExpression}" \
    --output table
}

[ "$#" -eq 2 ] || usage

case "$1" in
  setup) setup "$2" ;;
  deploy) deploy "$2" ;;
  *) usage ;;
esac
