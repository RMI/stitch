#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
spec_template="$repo_root/deployments/db/jobs/backup-job.yaml"

spec="$(mktemp)"
trap 'rm -f "$spec"' EXIT

az storage container create \
  --account-name "$LANE_STORAGE_ACCOUNT" \
  --account-key "$LANE_STORAGE_KEY" \
  --name backups \
  --output none

IFS=$'\t' read -r LANE_ENVIRONMENT_ID LANE_LOCATION <<<"$(
  az containerapp env show \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$AZURE_CONTAINER_APP_ENVIRONMENT" \
    --query "[id,location]" \
    --output tsv
)"
if [ -z "$LANE_ENVIRONMENT_ID" ] || [ -z "$LANE_LOCATION" ]; then
  echo "::error::Could not resolve the id and location of Container Apps environment '$AZURE_CONTAINER_APP_ENVIRONMENT' in '$AZURE_RESOURCE_GROUP'" >&2
  exit 1
fi
export LANE_ENVIRONMENT_ID LANE_LOCATION
echo "Environment $AZURE_CONTAINER_APP_ENVIRONMENT is in $LANE_LOCATION"

LANE_PGPASSWORD_JSON="$(printf '%s' "$LANE_PGPASSWORD" | jq -Rs .)"
LANE_STORAGE_KEY_JSON="$(printf '%s' "$LANE_STORAGE_KEY" | jq -Rs .)"
export LANE_PGPASSWORD_JSON LANE_STORAGE_KEY_JSON

envsubst '${LANE_LOCATION} ${LANE_ENVIRONMENT_ID} ${LANE_PGHOST} ${LANE_PGUSER} ${LANE_BACKUP_ENV} ${LANE_BACKUP_DATABASES} ${LANE_STORAGE_ACCOUNT} ${LANE_PGPASSWORD_JSON} ${LANE_STORAGE_KEY_JSON}' \
  <"$spec_template" \
  >"$spec"

if az containerapp job show \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$JOB_NAME" \
  --output none 2>/dev/null; then
  echo "Updating existing job $JOB_NAME"
  az containerapp job update \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$JOB_NAME" \
    --yaml "$spec" \
    --output none
else
  echo "Creating job $JOB_NAME"
  az containerapp job create \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$JOB_NAME" \
    --yaml "$spec" \
    --output none
fi

az containerapp job show \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$JOB_NAME" \
  --query "properties.configuration.{triggerType:triggerType,cron:scheduleTriggerConfig.cronExpression}" \
  --output table
