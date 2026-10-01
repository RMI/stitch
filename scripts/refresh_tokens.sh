#!/usr/bin/env bash
# Mint both bearer tokens with no browser and no args.
#
# Auth0 stamps lifetime and permissions into a token at issuance, so the API
# only needs to allow 30 days, and the client only needs the password grant,
# for the moment of the call. Both are widened, used, and put back.
#
# Put the service-account passwords in scripts/.env.auth0.pw first (chmod 600):
#   ETL_PASSWORD=...
#   LLM_PASSWORD=...
#
# The trap restores on success, failure and Ctrl-C alike. If it ever says it
# could not restore, fix that before walking away: leaving the API at 2592000
# hands every frontend user a 30-day token too.
set -euo pipefail
cd "$(dirname "$0")/.."

# shellcheck source=lib/common.sh
source scripts/lib/common.sh
stitch_load_env

# The Auth0 resource-server id of https://stitch-api.local. Per tenant, so it
# lives in .env.scripts rather than here.
API=${SCRIPTS__AUTH0_API_ID:-}
if [ -z "$API" ]; then
  echo "SCRIPTS__AUTH0_API_ID is not set. Add it to .env.scripts." >&2
  exit 1
fi

# The "stitch" SPA, the client that mints these. Already public in
# deployments/stitch-frontend/public/config.json.
APP=TS1V1soQbccAV1sitFFCfUaIlSwHD2S2

# Nothing below touches Auth0 when the tokens on disk are still good, so a
# re-push of unchanged tokens never widens the tenant. --force-auth0 overrides.
if ! ./scripts/bearer_tokens.py mint --needs-mint "$@"; then
  exec ./scripts/bearer_tokens.py mint "$@"
fi

OLD_LIFETIME=$(auth0 apis show "$API" --json | jq -r .token_lifetime)
OLD_GRANTS=$(auth0 apps show "$APP" --json | jq -c .grant_types)
echo "Current: token_lifetime=$OLD_LIFETIME grants=$OLD_GRANTS"

restore() {
  echo "Restoring token_lifetime=$OLD_LIFETIME grants=$OLD_GRANTS"
  auth0 apis update "$API" --data "{\"token_lifetime\":$OLD_LIFETIME}" >/dev/null ||
    echo "!! COULD NOT RESTORE token_lifetime -- set it to $OLD_LIFETIME by hand"
  auth0 apps update "$APP" --data "{\"grant_types\":$OLD_GRANTS}" >/dev/null ||
    echo "!! COULD NOT RESTORE grants -- set them to $OLD_GRANTS by hand"
}
trap restore EXIT

echo "Widening..."
auth0 apis update "$API" --data '{"token_lifetime":2592000}' >/dev/null
auth0 apps update "$APP" --data "{\"grant_types\":$(jq -cn --argjson g "$OLD_GRANTS" \
  '$g + ["password","http://auth0.com/oauth/grant-type/password-realm"] | unique')}" >/dev/null

./scripts/bearer_tokens.py mint "$@" # pass through --push [ENV ...]
