# Service-to-service auth (Auth0 M2M)

How internal services (`seed`, `entity-linkage`, `stitch-llm`, and — later —
ETL) authenticate to **`stitch-api`**, how to add a new service, and how to
debug it. This is the maintenance story that replaced hand-minted 30-day bearer
tokens.

## 1. How it works

### The flow

Internal services obtain **short-lived access tokens on demand** using the
OAuth2 **client-credentials** grant against Auth0, and send them to `stitch-api`
as `Authorization: Bearer <token>`:

```
service ──client_credentials──▶ Auth0 /oauth/token ──▶ short-lived JWT
service ──Bearer JWT──▶ stitch-api ──validates (JWKS) + reads `permissions`──▶ 200 / 401 / 403
```

No token is stored in a secret and rotated by hand. The token is fetched at
first use, cached in memory, and re-fetched reactively when the API returns 401
(expiry mid-flight). Implemented in `packages/stitch-client`
(`Auth0M2MAuth`, `fetch_auth_jwt`).

### Topology (one tenant, one API, one app per service)

| Piece | Value |
|-------|-------|
| Auth0 tenant / issuer | one tenant, e.g. `https://rmi-spd.us.auth0.com/` |
| API (resource server) / audience | one API, e.g. `https://stitch-api.local` |
| M2M applications | **one per calling service**: `stitch-seed-m2m`, `stitch-entity-linkage-m2m`, `stitch-llm-m2m` (ETL later) |
| Credential reuse | each app's single `client_id` / `client_secret` is **reused across every lane** (`development`, `staging`, `dress-rehearsal`) |

### Where each credential lives

- **`client_id`** — a GitHub **repository variable** (`SEED_AUTH_CLIENT_ID`,
  `ENTITY_LINKAGE_AUTH_CLIENT_ID`, `STITCH_LLM_AUTH_CLIENT_ID`). Not secret.
- **`client_secret`** — a GitHub **repository secret**
  (`SEED_AUTH_CLIENT_SECRET`, `ENTITY_LINKAGE_AUTH_CLIENT_SECRET`,
  `STITCH_LLM_AUTH_CLIENT_SECRET`).
- **audience / issuer** — reused from the lane's existing `AUTH_AUDIENCE` /
  `AUTH_ISSUER` (same tenant/API as the API validates against), surfaced through
  the `lane-config-validate` job outputs.

At runtime each service reads four environment variables:

```
STITCH_AUTH_CLIENT_ID
STITCH_AUTH_CLIENT_SECRET
STITCH_AUTH_AUDIENCE
STITCH_AUTH_ISSUER_URL
```

### Config-selected auth mode

The client picks its mode from the environment — there is no feature flag:

- **All four `STITCH_AUTH_*` present** → Auth0 M2M (real tokens).
- **All four absent** → **no `Authorization` header** attached. This is the
  local path: docker-compose runs `stitch-api` with `AUTH_DISABLED=true`, which
  accepts requests with no header. Against a real API it would fail loud (401).
- **Partially set** → the client raises `StitchAuthError` at startup — a
  half-config is a typo and must fail loud, not silently fall back.

`AUTH_DISABLED=true` is used **only** in local docker-compose. Every deployed
lane (`development` incl. PR previews + `main`, `staging`, `dress-rehearsal`)
runs `AUTH_DISABLED=false` with real M2M.

### The `permissions` claim (critical)

`stitch-api` authorizes routes off the token's **`permissions`** array claim
(`packages/stitch-auth/src/stitch/auth/validator.py`). For those permissions to
appear in an M2M token, the Auth0 **API** must have **RBAC enabled** and **"Add
Permissions in the Access Token"** turned on (token dialect
`access_token_authz`), and the M2M app must hold a **client grant** for those
scopes. Without the grant the token still validates (200) but carries an empty
`permissions` array → every permissioned route 403s, and source-gated data comes
back empty.

Permission strings are the constants in
`packages/stitch-auth/src/stitch/auth/permissions.py`:
`resource:read`, `resource:write`, `source:read:{rmi,gem,wm,llm}`,
`source:write`, `merge-candidate:{read,create,review}`,
`service:entity-linkage:run`, `service:llm:suggest`.

Every M2M app currently gets the **same full grant** (uniform broad grant — no
per-service least-privilege; accepted POC tradeoff).

### One-time Auth0 tenant setup

Done once with the Auth0 CLI (`brew install auth0/auth0-cli/auth0`,
`auth0 login`). Values below are examples — use the real tenant/API.

```bash
# 1. Confirm the current token shape (decode locally; NEVER paste the token
#    anywhere). sub ending in @clients => an M2M app already exists; a user sub
#    => today's permissions come from a role — capture that role's exact
#    permission list as the "full current permission set".

# 2. Ensure the API has RBAC + "Add Permissions in the Access Token".
auth0 api patch "resource-servers/<api_id>" \
  --data '{"enforce_policies": true, "token_dialect": "access_token_authz"}'

# 3. Ensure the API's scopes match permissions.py exactly (resource:read/write,
#    source:read:{rmi,gem,wm,llm}, source:write, merge-candidate:*,
#    service:entity-linkage:run, service:llm:suggest).

# 4. Create one M2M app per calling service (record each client_id/secret once).
auth0 apps create --name stitch-seed-m2m           --type m2m
auth0 apps create --name stitch-entity-linkage-m2m --type m2m
auth0 apps create --name stitch-llm-m2m            --type m2m

# 5. Grant each app the full permission set (uniform broad grant).
auth0 api post client-grants --data '{
  "client_id":"<id>",
  "audience":"<api-identifier>",
  "scope":["resource:read","resource:write","source:read:rmi","source:read:gem",
           "source:read:wm","source:read:llm","source:write",
           "merge-candidate:read","merge-candidate:create","merge-candidate:review",
           "service:entity-linkage:run","service:llm:suggest"]
}'

# 6. Verify a token carries gty=client-credentials and a populated permissions array.
auth0 test token -a <audience> -c <client_id> -s <secret>
```

Consider shortening the API token lifetime (e.g. 24h) now that tokens are
fetched on demand — reactive-on-401 refresh covers expiry.

### GitHub configuration (before enabling auth on `development`)

The `development` lane historically ran `AUTH_DISABLED=true` and may not carry
the `AUTH_*` variables. Do these **in order**, or `deploy-api` crash-loops:

1. Set `AUTH_ISSUER` / `AUTH_AUDIENCE` / `AUTH_JWKS_URI` on the `development`
   GitHub Environment (same values as `staging`).
2. Add the repo variables + secrets:
   - vars: `SEED_AUTH_CLIENT_ID`, `ENTITY_LINKAGE_AUTH_CLIENT_ID`, `STITCH_LLM_AUTH_CLIENT_ID`
   - secrets: `SEED_AUTH_CLIENT_SECRET`, `ENTITY_LINKAGE_AUTH_CLIENT_SECRET`, `STITCH_LLM_AUTH_CLIENT_SECRET`
3. Set `AUTH_DISABLED=false` on the `development` GitHub Environment.

## 2. Does a new service need its own auth?

**Yes — it needs its own M2M app** if it makes authenticated calls to
`stitch-api` (reads/writes resources, merge candidates, etc.).

**No** if it:

- only serves the frontend user flow (the browser carries the user's token), or
- only talks to non-Stitch systems, or
- runs solely under local `AUTH_DISABLED` and is never deployed against a real API.

## 3. Adding auth to a new service

1. **Create an M2M app** and grant it:
   `auth0 apps create --name stitch-<svc>-m2m --type m2m`, then
   `auth0 api post client-grants …` with the scopes it needs.
2. **Add CI config**: repo variable `<SVC>_AUTH_CLIENT_ID` and repo secret
   `<SVC>_AUTH_CLIENT_SECRET`.
3. **Thread the secret** through `deploy-container.yml`: it already accepts an
   optional `stitch-auth-client-secret` secret and injects it as
   `STITCH_AUTH_CLIENT_SECRET` when set — pass it from the service's deploy job.
4. **Set `STITCH_AUTH_*`** in the deploy job's `environment-variables`:
   `STITCH_AUTH_CLIENT_ID=${{ vars.<SVC>_AUTH_CLIENT_ID }}`,
   `STITCH_AUTH_AUDIENCE=${{ needs.lane-config-validate.outputs.auth-audience }}`,
   `STITCH_AUTH_ISSUER_URL=${{ needs.lane-config-validate.outputs.auth-issuer }}`.
5. **Build the client** via
   `AsyncStitchClient.from_service_env(api_base_url=<your base url>)` — do not
   hand-roll headers. Keep your own base-url env var (do not adopt
   `STITCH_API_BASE_URL`).
6. **Add the startup validator** in your lifespan:
   `await validate_downstream_auth_at_startup(api_base_url=<your base url>)` so
   bad credentials fail fast at boot.
7. (Optional) surface the four `STITCH_AUTH_*` in your settings + a derived
   `auth_mode` (`"m2m"` / `"none"`) property for `/health` reporting.

## 4. Troubleshooting

**401 Unauthorized**
- Missing/expired token, or wrong `audience`/`issuer`. Confirm `STITCH_AUTH_AUDIENCE`
  matches the API identifier and `STITCH_AUTH_ISSUER_URL` matches the tenant
  (trailing slash and all).
- The service started before creds were set (partial config) — check the
  startup log for `StitchAuthError`.

**200 but empty data / unexpected 403**
- The app has **no client grant** (or the API lacks RBAC + "Add Permissions in
  the Access Token") → the token's `permissions` array is empty. All
  permissioned routes 403, and `source:read:*`-gated results filter to nothing.
  Fix the grant / API settings (§1) and re-issue a token.

**API crash-loop right after flipping `AUTH_DISABLED=false`**
- The lane is missing `AUTH_ISSUER` / `AUTH_AUDIENCE` / `AUTH_JWKS_URI`. The
  API's `validate_auth_config_at_startup()` fails fast. Set them (§1) before
  flipping the flag.

**Auth0 `/oauth/token` rate limits (429)**
- Each boot makes two token fetches (startup validator + first real request, on
  separate caches). Under heavy churn (many PR previews) you may hit Auth0's
  rate limit; back off / stagger deploys.

**Rotation & cross-lane replay**
- Credentials are shared across lanes by design, so a leaked `client_secret` (or
  token) is valid against **all** lanes. Rotation must therefore be **atomic
  across all three GitHub Environments** — rotate the Auth0 secret and update
  every lane's `*_AUTH_CLIENT_SECRET` together.

## Notes / current tradeoffs (POC-accepted)

- Uniform broad grant (no per-service least-privilege).
- `client_secret` stored as plaintext Container App env (no Key Vault reference);
  graduation path is Key Vault references.
- M2M `…@clients` subjects get JIT-provisioned `users` rows (null name/email).
- ETL (`stitch-etl-poc`) still authenticates with the legacy hand-minted bearer
  (`STITCH_CLIENT_PRIVILEGED_BEARER_TOKEN`, injected as `STITCH_CLIENT_BEARER_TOKEN`
  by `deploy-etl`). The legacy `env_bearer_token_headers_provider()` helper has
  been **removed from `stitch-client` in this repo**; ETL builds from a pinned
  `stitch-client`, so it keeps its own copy until it migrates to M2M (a separate
  PR that will also drop the `STITCH_CLIENT_*_BEARER_TOKEN` CI wiring).
