#!/usr/bin/env bash
#
# Interactive auth testing demo.
# Walks through each auth scenario against the local API + localauth0.
#
# Prerequisites:
#   1. .env configured with AUTH_DISABLED=false and localauth0 settings
#   2. Stack running: docker compose -f docker-compose.yml -f docker-compose.local.yml --profile auth-test up
#
# Usage:
#   bash dev/auth-demo.sh

set -euo pipefail

API=localhost:8000/api/v1
OIDC=localhost:3100

BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
RESET='\033[0m'

# ── helpers ──────────────────────────────────────────────────────────

step_number=0

wait_for_enter() {
    echo ""
    read -rp "$(echo -e "${DIM}Press Enter to run...${RESET}")"
}

show_step() {
    step_number=$((step_number + 1))
    local title=$1
    local description=$2
    local expect=$3

    echo ""
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${BOLD}  Scenario ${step_number}: ${title}${RESET}"
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "  ${description}"
    echo -e "  ${CYAN}Expected: ${expect}${RESET}"
}

show_cmd() {
    echo -e "\n  ${DIM}\$${RESET} $1"
}

run_curl() {
    local label=$1
    shift
    echo ""
    # Run curl, capture status code on last line
    local response
    response=$(curl -s -w "\n%{http_code}" "$@")
    local http_code
    http_code=$(echo "$response" | tail -1)
    local body
    body=$(echo "$response" | sed '$d')

    if [ -n "$body" ]; then
        echo -e "  ${DIM}Body:${RESET}"
        # Pretty-print JSON if jq is available, otherwise raw
        if command -v jq &>/dev/null; then
            echo "$body" | jq . 2>/dev/null | sed 's/^/    /' || echo "    $body"
        else
            echo "    $body"
        fi
    fi
    echo -e "  ${BOLD}HTTP ${http_code}${RESET}"
}

# ── preflight checks ────────────────────────────────────────────────

echo -e "${BOLD}Auth Testing Demo${RESET}"
echo -e "${DIM}Testing API at ${API}, OIDC at ${OIDC}${RESET}"
echo ""

echo -n "Checking API... "
if curl -sf -o /dev/null "${API}/health" 2>/dev/null; then
    echo -e "${GREEN}OK${RESET}"
else
    echo -e "${RED}FAILED${RESET}"
    echo "  API is not reachable at ${API}. Is the stack running?"
    exit 1
fi

echo -n "Checking localauth0... "
if curl -sf -o /dev/null "${OIDC}/.well-known/openid-configuration" 2>/dev/null; then
    echo -e "${GREEN}OK${RESET}"
else
    echo -e "${RED}FAILED${RESET}"
    echo "  localauth0 is not reachable at ${OIDC}."
    echo "  Start with: docker compose -f docker-compose.yml -f docker-compose.local.yml --profile auth-test up"
    exit 1
fi

# ── scenario 1: health endpoint (no auth required) ──────────────────

show_step \
    "Health endpoint (no auth)" \
    "The /health endpoint is always open — no token required." \
    "200"
show_cmd "curl ${API}/health"
wait_for_enter
run_curl "health" "${API}/health"

# ── scenario 2: no authorization header ─────────────────────────────

show_step \
    "No Authorization header" \
    "A request with no token at all. The API checks for the Authorization\n  header and rejects the request before any JWT parsing happens." \
    "401"
show_cmd "curl ${API}/resources/"
wait_for_enter
run_curl "no-auth" "${API}/resources/"

# ── scenario 3: malformed header (wrong scheme) ─────────────────────

show_step \
    "Malformed Authorization header" \
    "Using 'Basic' instead of 'Bearer'. The API parses the scheme and\n  rejects anything that isn't 'Bearer <token>'." \
    "401"
show_cmd "curl -H 'Authorization: Basic xyz' ${API}/resources/"
wait_for_enter
run_curl "basic-auth" "${API}/resources/" -H "Authorization: Basic xyz"

# ── scenario 4: garbage token (wrong signing key) ───────────────────

show_step \
    "Garbage token (invalid JWT)" \
    "A string that isn't a valid JWT. The JWKS client can't find a matching\n  key ID, so signature verification fails." \
    "401"
show_cmd "curl -H 'Authorization: Bearer not.a.real.jwt' ${API}/resources/"
wait_for_enter
run_curl "garbage" "${API}/resources/" -H "Authorization: Bearer not.a.real.jwt"

# ── scenario 5: wrong audience ──────────────────────────────────────

show_step \
    "Valid JWT, wrong audience" \
    "A properly signed token from localauth0, but issued for 'wrong-audience'\n  instead of 'stitch-api-local'. The API validates the 'aud' claim and rejects it." \
    "401"

echo -e "\n  ${DIM}Fetching token with audience='wrong-audience'...${RESET}"
WRONG_TOKEN=$(curl -s -X POST "${OIDC}/oauth/token" \
    -H "Content-Type: application/json" \
    -d '{"client_id":"client_id","client_secret":"client_secret","audience":"wrong-audience","grant_type":"client_credentials"}' \
    | jq -r '.access_token' 2>/dev/null) || true

if [ -z "$WRONG_TOKEN" ] || [ "$WRONG_TOKEN" = "null" ]; then
    echo -e "  ${RED}Failed to get token from localauth0${RESET}"
    exit 1
fi
echo -e "  ${GREEN}Got token${RESET} ${DIM}(${#WRONG_TOKEN} chars)${RESET}"

show_cmd "curl -H 'Authorization: Bearer \$WRONG_TOKEN' ${API}/resources/"
wait_for_enter
run_curl "wrong-aud" "${API}/resources/" -H "Authorization: Bearer ${WRONG_TOKEN}"

# ── scenario 6: valid token, first request (JIT provisioning) ───────

show_step \
    "Valid token — first request (JIT user creation)" \
    "A properly signed token with the correct audience. On the first\n  authenticated request, the API creates a new user row in the database\n  from the token's sub/name/email claims." \
    "200 + user JIT-created in DB"

echo -e "\n  ${DIM}Fetching token with audience='stitch-api-local'...${RESET}"
TOKEN=$(curl -s -X POST "${OIDC}/oauth/token" \
    -H "Content-Type: application/json" \
    -d '{"client_id":"client_id","client_secret":"client_secret","audience":"stitch-api-local","grant_type":"client_credentials"}' \
    | jq -r '.access_token' 2>/dev/null) || true

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo -e "  ${RED}Failed to get token from localauth0${RESET}"
    exit 1
fi
echo -e "  ${GREEN}Got token${RESET} ${DIM}(${#TOKEN} chars)${RESET}"

show_cmd "curl -H 'Authorization: Bearer \$TOKEN' ${API}/resources/"
wait_for_enter
run_curl "valid-first" "${API}/resources/" -H "Authorization: Bearer ${TOKEN}"

# ── scenario 7: valid token, repeat request ─────────────────────────

show_step \
    "Valid token — repeat request (user already exists)" \
    "Same token again. The API finds the existing user by 'sub' and updates\n  name/email from the token claims. No new row is created." \
    "200 + user info updated"
show_cmd "curl -H 'Authorization: Bearer \$TOKEN' ${API}/resources/"
wait_for_enter
run_curl "valid-repeat" "${API}/resources/" -H "Authorization: Bearer ${TOKEN}"

# ── done ─────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}${BOLD}  All scenarios complete.${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  Verify JIT user in Adminer: ${CYAN}http://localhost:8081${RESET}"
echo -e "  Try Swagger UI:             ${CYAN}http://localhost:8000/docs${RESET}"
echo ""
