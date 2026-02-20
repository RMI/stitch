# Local Auth Testing Guide

This guide covers how to test JWT authentication locally using [localauth0](https://github.com/primait/localauth0), a lightweight mock OIDC server.

## How Auth Works in Production

When `AUTH_DISABLED=false`, every request (except `/health`) goes through a JWT validation pipeline that mirrors a real Auth0 deployment:

1. **Header parsing** — extract the `Bearer <token>` from the `Authorization` header
2. **JWKS fetch** — retrieve the signing key from the OIDC provider's `/.well-known/jwks.json` endpoint (cached for 600s)
3. **Signature verification** — verify the token was signed with the provider's private key (RS256)
4. **Claims validation** — the following claims are required and checked:
   | Claim | Check |
   |-------|-------|
   | `exp` | Token has not expired (with 30s clock skew tolerance) |
   | `nbf` | Token is not used before its "not before" time |
   | `iss` | Issuer matches `AUTH_ISSUER` |
   | `aud` | Audience matches `AUTH_AUDIENCE` |
   | `sub` | Subject is present (unique user identifier) |
5. **User provisioning** — the `sub` claim is looked up in the `users` table. On first login, a user row is JIT-created; on subsequent logins, `name` and `email` are updated from the token claims.

Any failure at steps 1-4 returns a **401** with `WWW-Authenticate: Bearer`.

**Production guardrail:** `AUTH_DISABLED=true` is blocked at startup when `ENVIRONMENT=prod`.

## Default Mode (auth disabled)

By default, `AUTH_DISABLED=true` in `.env`. All API requests are accepted without tokens, and a hardcoded dev user (`sub="dev|local-placeholder"`) is injected. This is the normal local development experience.

## Enabling Auth Testing

### 1. Configure environment

Update `.env` with the auth-test settings:

```
AUTH_DISABLED=false
AUTH_ISSUER=http://localauth0:3000/
AUTH_AUDIENCE=stitch-api-local
AUTH_JWKS_URI=http://localauth0:3000/.well-known/jwks.json
```

### 2. Start the stack

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml --profile auth-test up --build
```

This starts the normal stack (db, api, frontend) plus `localauth0` on port 3100 (host) / 3000 (Docker network).

### 3. Verify localauth0 is running

```bash
curl -s localhost:3100/.well-known/openid-configuration | jq .
```

## Getting Tokens

Tokens from localauth0 are valid for **24 hours** (`expires_in: 86400`). Expired-token validation is covered by unit tests in `packages/stitch-auth/tests/test_validator_unit.py`.

### Valid token (correct audience)

```bash
TOKEN=$(curl -s -X POST localhost:3100/oauth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id":"client_id","client_secret":"client_secret","audience":"stitch-api-local","grant_type":"client_credentials"}' \
  | jq -r '.access_token')

echo $TOKEN
```

### Token with wrong audience

```bash
WRONG_TOKEN=$(curl -s -X POST localhost:3100/oauth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id":"client_id","client_secret":"client_secret","audience":"wrong-audience","grant_type":"client_credentials"}' \
  | jq -r '.access_token')
```

## Test Scenarios

| #   | Scenario                          | Command                                                                           | Expected               |
| --- | --------------------------------- | --------------------------------------------------------------------------------- | ---------------------- |
| 1   | No Authorization header           | `curl localhost:8000/api/v1/resources/`                                           | 401                    |
| 2   | Malformed header                  | `curl -H "Authorization: Basic xyz" localhost:8000/api/v1/resources/`             | 401                    |
| 3   | Garbage token (wrong signing key) | `curl -H "Authorization: Bearer not.a.real.jwt" localhost:8000/api/v1/resources/` | 401                    |
| 4   | Wrong audience                    | `curl -H "Authorization: Bearer $WRONG_TOKEN" localhost:8000/api/v1/resources/`   | 401                    |
| 5   | Valid token, first request        | `curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/resources/`         | 200, user JIT-created  |
| 6   | Valid token, repeat request       | Same as #5                                                                        | 200, user info updated |
| 7   | Health endpoint (no auth)         | `curl localhost:8000/api/v1/health`                                               | 200 always             |

**Not testable with localauth0:** wrong-issuer rejection (localauth0's issuer is fixed). This is validated in production and covered by unit tests (`test_validator_unit.py::test_wrong_issuer_raises`).

### Interactive demo script

Run the scenarios interactively with step-by-step confirmation:

```bash
bash dev/auth-demo.sh
```

### Running the scenarios manually

```bash
# 1. No token
curl -s -o /dev/null -w "%{http_code}" localhost:8000/api/v1/resources/
# → 401

# 2. Malformed header
curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Basic xyz" localhost:8000/api/v1/resources/
# → 401

# 3. Garbage token
curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer not.a.real.jwt" localhost:8000/api/v1/resources/
# → 401

# 4. Wrong audience
WRONG_TOKEN=$(curl -s -X POST localhost:3100/oauth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id":"client_id","client_secret":"client_secret","audience":"wrong-audience","grant_type":"client_credentials"}' \
  | jq -r '.access_token')
curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $WRONG_TOKEN" localhost:8000/api/v1/resources/
# → 401

# 5. Valid token (first request — JIT user creation)
TOKEN=$(curl -s -X POST localhost:3100/oauth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id":"client_id","client_secret":"client_secret","audience":"stitch-api-local","grant_type":"client_credentials"}' \
  | jq -r '.access_token')
curl -s -w "\n%{http_code}" -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/resources/
# → 200

# 6. Same token again (user already exists)
curl -s -w "\n%{http_code}" -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/resources/
# → 200

# 7. Health endpoint (always open)
curl -s -o /dev/null -w "%{http_code}" localhost:8000/api/v1/health
# → 200
```

## Verifying JIT User Provisioning

After a successful authenticated request, verify the user was created in the database via Adminer:

1. Open http://localhost:8081
2. Connect to `stitch` database (user: `postgres`, password: `postgres`)
3. Browse the `users` table
4. You should see a row with `sub = "mock|dev-user-1"`

## Using Swagger UI

1. Open http://localhost:8000/docs
2. Click the "Authorize" button (lock icon)
3. Enter a Bearer token obtained from localauth0
4. Click "Authorize"
5. All subsequent "Try it out" requests will include the token

## CORS and Browser Requests

The API's CORS middleware explicitly allows the `Authorization` header from the configured `FRONTEND_ORIGIN_URL`. Browser-based requests from the frontend will include the JWT in the `Authorization` header and pass CORS preflight checks. To test this flow, use the frontend at http://localhost:3000 after authenticating via Swagger or configure the frontend to send tokens.

## localauth0 Configuration

The mock server is configured via `dev/localauth0.toml`:

- **Issuer**: `http://localauth0:3000/` (matches `AUTH_ISSUER`)
- **User**: `sub=mock|dev-user-1`, name "Dev User", email `dev@example.com`
- **Audiences**: `stitch-api-local` (valid) and `wrong-audience` (for testing rejection)
- **Port**: 3000 inside Docker, mapped to 3100 on the host

## Configuring Real Auth0

For staging or production, replace the environment variables with your Auth0 tenant values:

```
AUTH_DISABLED=false
AUTH_ISSUER=https://your-tenant.auth0.com/
AUTH_AUDIENCE=your-api-audience
AUTH_JWKS_URI=https://your-tenant.auth0.com/.well-known/jwks.json
```
