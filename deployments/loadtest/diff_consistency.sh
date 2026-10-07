#!/usr/bin/env bash
# Compare captured (normalized) JSON responses across branches vs a baseline.
# Files: <OUTDIR>/<branch>__<perm>__<ep>.json
#
# Usage: diff_consistency.sh <consistency-dir> [baseline] [branch ...]
#   baseline  defaults to "main"
#   branch... defaults to every other <branch> prefix found in the directory
set -euo pipefail
OUTDIR="${1:?usage: diff_consistency.sh <dir> [baseline] [branch...]}"
cd "$OUTDIR"
shift
BASELINE="${1:-main}"
[ $# -ge 1 ] && shift || true
BRANCHES=("$@")
if [ ${#BRANCHES[@]} -eq 0 ]; then
  while IFS= read -r b; do
    [ -n "$b" ] && [ "$b" != "$BASELINE" ] && BRANCHES+=("$b")
  done < <(ls -1 ./*__*.json 2>/dev/null | sed 's|^\./||; s/__.*//' | sort -u)
fi

same=0; diff=0; missing=0
for base in "${BASELINE}"__*.json; do
  [ -e "$base" ] || continue
  rest="${base#${BASELINE}__}"          # <perm>__<ep>.json
  for br in "${BRANCHES[@]}"; do
    other="${br}__${rest}"
    if [ ! -e "$other" ]; then
      echo "MISSING  ${other}"; missing=$((missing+1)); continue
    fi
    if diff -q "$base" "$other" >/dev/null 2>&1; then
      same=$((same+1))
    else
      diff=$((diff+1))
      echo "DIFFERS  ${BASELINE} vs ${br}: ${rest}"
      # `diff` exits non-zero on a difference; keep set -e from aborting the loop.
      { diff "$base" "$other" || true; } | head -6 | sed 's/^/    /'
    fi
  done
done
echo ""
echo "baseline=${BASELINE} branches=[${BRANCHES[*]:-none}]"
echo "consistency: identical=${same}  differing=${diff}  missing=${missing}"
