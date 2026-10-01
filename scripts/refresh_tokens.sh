#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/lib/common.sh
stitch_load_env

API=${SCRIPTS__AUTH0_API_ID:-}
if [ -z "$API" ]; then
  echo "SCRIPTS__AUTH0_API_ID is not set. Add it to .env.scripts." >&2
  exit 1
fi

APP=TS1V1soQbccAV1sitFFCfUaIlSwHD2S2

if ! ./scripts/bearer_tokens.py mint --needs-mint "$@"; then
  exec ./scripts/bearer_tokens.py mint "$@"
fi

OLD_LIFETIME=$(auth0 apis show "$API" --json | jq -r .token_lifetime)
OLD_GRANTS=$(auth0 apps show "$APP" --json | jq -c .grant_types)
echo "Current: token_lifetime=$OLD_LIFETIME grants=$OLD_GRANTS"

restore() {
  echo "Restoring token_lifetime=$OLD_LIFETIME grants=$OLD_GRANTS"
  auth0 apis update "$API" --data "{\"token_lifetime\":$OLD_LIFETIME}" >/dev/null ||
    echo "!! COULD NOT RESTORE token_lifetime -- set it to $OLD_LIFETIME by hand; until then every frontend login gets a 30-day token" >&2
  auth0 apps update "$APP" --data "{\"grant_types\":$OLD_GRANTS}" >/dev/null ||
    echo "!! COULD NOT RESTORE grants -- set them to $OLD_GRANTS by hand" >&2
}
trap restore EXIT

echo "Widening..."
auth0 apis update "$API" --data '{"token_lifetime":2592000}' >/dev/null
auth0 apps update "$APP" --data "{\"grant_types\":$(jq -cn --argjson g "$OLD_GRANTS" \
  '$g + ["password","http://auth0.com/oauth/grant-type/password-realm"] | unique')}" >/dev/null

./scripts/bearer_tokens.py mint "$@"
