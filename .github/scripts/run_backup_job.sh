#!/usr/bin/env bash
# Run one database backup as a Container Apps job: create a throwaway job from
# deployments/db-backup/job.yaml, start it, wait for the execution to finish, then
# delete the job.
#
# Every run gets its own job (JOB_NAME must be unique per run), so concurrent runs
# never share state and one run cannot change what another one backs up.
#
# Required environment: JOB_NAME, AZURE_RESOURCE_GROUP, AZURE_CONTAINER_APP_ENVIRONMENT,
# and the LANE_* values rendered into the job spec (see the envsubst list below).
# Optional: POLL_INTERVAL_SECONDS (default 15), WAIT_TIMEOUT_SECONDS (default 2400).
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
spec_template="$repo_root/deployments/db-backup/job.yaml"

: "${JOB_NAME:?Missing JOB_NAME (must be unique per run)}"
: "${AZURE_RESOURCE_GROUP:?Missing AZURE_RESOURCE_GROUP}"
: "${AZURE_CONTAINER_APP_ENVIRONMENT:?Missing AZURE_CONTAINER_APP_ENVIRONMENT}"
: "${LANE_BACKUP_IMAGE:?Missing LANE_BACKUP_IMAGE}"
: "${LANE_BACKUP_IDENTITY_NAME:?Missing LANE_BACKUP_IDENTITY_NAME}"
: "${LANE_PGPASSWORD:?Missing LANE_PGPASSWORD}"

poll_interval="${POLL_INTERVAL_SECONDS:-15}"
wait_timeout="${WAIT_TIMEOUT_SECONDS:-2400}"

spec="$(mktemp)"

cleanup() {
  rm -f "$spec"
  # Delete the job whether the run passed or failed. Check first so a run that
  # never got as far as creating it does not print a misleading error.
  if az containerapp job show \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$JOB_NAME" \
    --output none 2>/dev/null; then
    if ! az containerapp job delete \
      --resource-group "$AZURE_RESOURCE_GROUP" \
      --name "$JOB_NAME" \
      --yes \
      --output none; then
      echo "::warning::Could not delete backup job $JOB_NAME in $AZURE_RESOURCE_GROUP; delete it by hand" >&2
    fi
  fi
}
trap cleanup EXIT

environment_json="$(
  az containerapp env show \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$AZURE_CONTAINER_APP_ENVIRONMENT" \
    --query "{id: id, location: location}" \
    --output json
)"
LANE_ENVIRONMENT_ID="$(jq -r '.id // empty' <<<"$environment_json")"
LANE_LOCATION="$(jq -r '.location // empty' <<<"$environment_json")"
if [ -z "$LANE_ENVIRONMENT_ID" ] || [ -z "$LANE_LOCATION" ]; then
  echo "::error::Could not resolve the id and location of Container Apps environment '$AZURE_CONTAINER_APP_ENVIRONMENT' in '$AZURE_RESOURCE_GROUP'" >&2
  exit 1
fi
export LANE_ENVIRONMENT_ID LANE_LOCATION
echo "Environment $AZURE_CONTAINER_APP_ENVIRONMENT is in $LANE_LOCATION"

identity_json="$(
  az identity show \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$LANE_BACKUP_IDENTITY_NAME" \
    --query "{id: id, clientId: clientId}" \
    --output json
)"
LANE_BACKUP_IDENTITY_ID="$(jq -r '.id // empty' <<<"$identity_json")"
LANE_BACKUP_IDENTITY_CLIENT_ID="$(jq -r '.clientId // empty' <<<"$identity_json")"
if [ -z "$LANE_BACKUP_IDENTITY_ID" ] || [ -z "$LANE_BACKUP_IDENTITY_CLIENT_ID" ]; then
  echo "::error::Could not resolve the id and client id of managed identity '$LANE_BACKUP_IDENTITY_NAME' in '$AZURE_RESOURCE_GROUP'" >&2
  exit 1
fi
export LANE_BACKUP_IDENTITY_ID LANE_BACKUP_IDENTITY_CLIENT_ID
echo "Backup job will run as managed identity $LANE_BACKUP_IDENTITY_NAME"

LANE_PGPASSWORD_JSON="$(printf '%s' "$LANE_PGPASSWORD" | jq -Rs .)"
export LANE_PGPASSWORD_JSON

# The single quotes are deliberate: envsubst expands only the variables named here,
# so nothing else in the spec is touched. Keep this list in step with job.yaml.
# shellcheck disable=SC2016
envsubst '${LANE_LOCATION} ${LANE_ENVIRONMENT_ID} ${LANE_BACKUP_IMAGE} ${LANE_BACKUP_IDENTITY_ID} ${LANE_BACKUP_IDENTITY_CLIENT_ID} ${LANE_PGHOST} ${LANE_PGPORT} ${LANE_PGUSER} ${LANE_BACKUP_ENV} ${LANE_BACKUP_KIND} ${LANE_BACKUP_DATABASES} ${LANE_STORAGE_ACCOUNT} ${LANE_PGPASSWORD_JSON}' \
  <"$spec_template" \
  >"$spec"

echo "Creating job $JOB_NAME (image $LANE_BACKUP_IMAGE, databases: $LANE_BACKUP_DATABASES)"
az containerapp job create \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$JOB_NAME" \
  --yaml "$spec" \
  --output none

execution_name="$(
  az containerapp job start \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$JOB_NAME" \
    --query name \
    --output tsv
)"
if [ -z "$execution_name" ]; then
  echo "::error::Started job $JOB_NAME but could not read the execution name" >&2
  exit 1
fi
echo "Started execution $execution_name"

# Wait for the execution to reach a final state.
result=""
elapsed=0
while [ -z "$result" ]; do
  if ! status="$(
    az containerapp job execution show \
      --resource-group "$AZURE_RESOURCE_GROUP" \
      --name "$JOB_NAME" \
      --job-execution-name "$execution_name" \
      --query properties.status \
      --output tsv
  )"; then
    echo "Could not read the status of $execution_name; will retry" >&2
    status="Unknown"
  fi
  echo "[${elapsed}s] $execution_name: $status"

  case "$status" in
    Succeeded) result="succeeded" ;;
    Failed | Stopped | Degraded) result="failed" ;;
    *)
      if [ "$elapsed" -ge "$wait_timeout" ]; then
        echo "::error::Timed out after ${elapsed}s waiting for $execution_name (last status: $status)" >&2
        result="timeout"
      else
        sleep "$poll_interval"
        elapsed=$((elapsed + poll_interval))
      fi
      ;;
  esac
done

# Container logs are best effort: the command is in preview and logs can lag the
# execution. The full logs are also in the environment's Log Analytics workspace.
echo "::group::Container logs for $execution_name (best effort)"
if ! az containerapp job logs show \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$JOB_NAME" \
  --execution "$execution_name" \
  --container backup \
  --format text \
  --tail 200; then
  echo "Could not fetch logs for $execution_name; look them up in the Container Apps environment's Log Analytics workspace" >&2
fi
echo "::endgroup::"

if [ "$result" != "succeeded" ]; then
  echo "::error::Backup execution $execution_name did not succeed ($result)" >&2
  exit 1
fi
echo "Backup execution $execution_name succeeded"
