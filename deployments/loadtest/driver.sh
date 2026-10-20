#!/usr/bin/env bash
# HTTP load driver for a read-perf comparison across branches.
#
# Drives a set of read endpoints single-stream (warmup discarded, then measured),
# tagging every request with X-Stitch-Perf-Scenario so the aggregator (agg.py) and
# tools/analyze_logs.py --group-by scenario can compare branch/volume/profile/endpoint
# from one log.
#
# Env:
#   BASE      base url (default http://localhost:8000/api/v1)
#   TOKEN     bearer token (optional; omit for AUTH_DISABLED or in-process runs)
#   BRANCH    label, e.g. main|a|b
#   VOL       label, e.g. 1k
#   PERM      label, e.g. all8|public6|... (free-form)
#   WARMUP    warmup requests per endpoint (default 20)
#   MEASURE   measured requests per endpoint (default 100)
#   EPS_FILE  optional file of "label|path" lines (one per line) to replace the
#             default endpoint set; a literal {RID} in a path is substituted with
#             a sampled resource id (lines needing an id are skipped if none found).
set -euo pipefail

BASE="${BASE:-http://localhost:8000/api/v1}"
BRANCH="${BRANCH:-?}"
VOL="${VOL:-?}"
PERM="${PERM:-?}"
WARMUP="${WARMUP:-20}"
MEASURE="${MEASURE:-100}"

AUTH=()
[ -n "${TOKEN:-}" ] && AUTH=(-H "Authorization: Bearer ${TOKEN}")

req() {  # req <path>
  curl -s -o /dev/null ${AUTH[@]+"${AUTH[@]}"} "$@"
}

# Sanity: one request must not be 401/403.
code=$(curl -s -o /dev/null -w '%{http_code}' ${AUTH[@]+"${AUTH[@]}"} "${BASE}/oil-gas-fields/?page=1&page_size=1")
echo "[driver] sanity ${BASE} perm=${PERM} -> HTTP ${code}"
if [ "$code" = "401" ] || [ "$code" = "403" ]; then
  echo "[driver] ABORT: auth rejected (need token or AUTH_DISABLED)"; exit 2
fi

# Sample a real resource id for {RID} / the default detail endpoints.
RID=$(curl -s ${AUTH[@]+"${AUTH[@]}"} "${BASE}/oil-gas-fields/?page=1&page_size=1" | jq -r '.items[0].id // empty')
echo "[driver] sample resource id=${RID:-<none>}"

# Endpoint set: label|path. Override with EPS_FILE, else the default read surface.
declare -a EPS=()
if [ -n "${EPS_FILE:-}" ] && [ -f "${EPS_FILE}" ]; then
  while IFS= read -r line; do [ -n "$line" ] && EPS+=("$line"); done < "${EPS_FILE}"
else
  EPS=(
    "list|/oil-gas-fields/?page=1&page_size=50"
    "list_ps200|/oil-gas-fields/?page=1&page_size=200"
    "list_sort|/oil-gas-fields/?page=1&page_size=50&sort_by=name"
    "list_q|/oil-gas-fields/?page=1&page_size=50&q=field"
    "filter_options|/oil-gas-fields/filter-options"
    "id|/oil-gas-fields/{RID}"
    "detail|/oil-gas-fields/{RID}/detail"
    "field_sources|/oil-gas-fields/{RID}/fields/name/sources"
  )
fi

for entry in "${EPS[@]}"; do
  ep="${entry%%|*}"; path="${entry#*|}"
  if [[ "$path" == *"{RID}"* ]]; then
    [ -z "${RID:-}" ] && { echo "[driver] skip ep=${ep} (no resource id)"; continue; }
    path="${path//\{RID\}/$RID}"
  fi
  scen="b=${BRANCH};vol=${VOL};perm=${PERM};ep=${ep}"
  # warmup (discarded)
  for _ in $(seq "$WARMUP"); do req "${BASE}${path}" >/dev/null 2>&1 || true; done
  # measured (tagged)
  for _ in $(seq "$MEASURE"); do req -H "X-Stitch-Perf-Scenario: ${scen}" "${BASE}${path}"; done
  echo "[driver] done ep=${ep} (warmup=${WARMUP} measure=${MEASURE}) scen=${scen}"
done
echo "[driver] complete perm=${PERM}"
