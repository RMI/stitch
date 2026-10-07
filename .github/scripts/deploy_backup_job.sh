#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
spec_template="$repo_root/deployments/db/jobs/backup-job.yaml"

spec="$(mktemp)"
trap 'rm -f "$spec"' EXIT

az storage container create \
  --account-name "$LANE_STORAGE_ACCOUNT" \
  --auth-mode login \
  --name backups \
  --output none

LANE_ENVIRONMENT_ID="$(
  az containerapp env show \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$AZURE_CONTAINER_APP_ENVIRONMENT" \
    --query id \
    --output tsv
)"
if [ -z "$LANE_ENVIRONMENT_ID" ]; then
  echo "::error::Could not resolve the id of Container Apps environment '$AZURE_CONTAINER_APP_ENVIRONMENT' in '$AZURE_RESOURCE_GROUP'" >&2
  exit 1
fi
export LANE_ENVIRONMENT_ID
echo "Environment $AZURE_CONTAINER_APP_ENVIRONMENT resolved; the job inherits its location"

LANE_PGPASSWORD_JSON="$(printf '%s' "$LANE_PGPASSWORD" | jq -Rs .)"
export LANE_PGPASSWORD_JSON

envsubst '${LANE_ENVIRONMENT_ID} ${LANE_PGHOST} ${LANE_PGUSER} ${LANE_BACKUP_ENV} ${LANE_BACKUP_DATABASES} ${LANE_STORAGE_ACCOUNT} ${LANE_PGPASSWORD_JSON} ${LANE_BACKUP_IDENTITY_ID} ${LANE_BACKUP_IDENTITY_CLIENT_ID}' \
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
