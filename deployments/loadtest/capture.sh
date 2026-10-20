#!/usr/bin/env bash
# Capture normalized JSON responses for the consistency comparison.
# Writes <OUTDIR>/<BRANCH>__<perm>__<ep>.json (jq-canonicalized, metadata stripped).
#
# Env: BASE, TOKEN (optional), BRANCH, PERM (label), OUTDIR
set -euo pipefail
BASE="${BASE:-http://localhost:8000/api/v1}"
BRANCH="${BRANCH:-?}"
PERM="${PERM:-all8}"
OUTDIR="${OUTDIR:?set OUTDIR}"
mkdir -p "$OUTDIR"

AUTH=()
[ -n "${TOKEN:-}" ] && AUTH=(-H "Authorization: Bearer ${TOKEN}")

# Recursively drop non-deterministic seed metadata, then sort keys.
NORM='walk(if type=="object" then del(.run_id, .observed_at) else . end)'

get() { curl -s ${AUTH[@]+"${AUTH[@]}"} "$@"; }
save() { # save <ep-label> <path>
  local ep="$1" path="$2"
  get "${BASE}${path}" | jq -S "$NORM" > "${OUTDIR}/${BRANCH}__${PERM}__${ep}.json" 2>/dev/null \
    && echo "[capture] ${BRANCH}/${PERM}/${ep}" \
    || echo "[capture] FAILED ${BRANCH}/${PERM}/${ep}"
}

# Stable-ordered list (all pages would be ideal; page 1 large page for smoke).
save "list_p1"        "/oil-gas-fields/?page=1&page_size=200&sort_by=name"
save "filter_options" "/oil-gas-fields/filter-options"

# A few detail records by id (first 3 ids on the sorted first page).
IDS=$(get "${BASE}/oil-gas-fields/?page=1&page_size=200&sort_by=name" | jq -r '.items[0:3][].id // empty')
for rid in $IDS; do
  save "id_${rid}"     "/oil-gas-fields/${rid}"
  save "detail_${rid}" "/oil-gas-fields/${rid}/detail"
done
echo "[capture] complete ${BRANCH}/${PERM} -> ${OUTDIR}"
