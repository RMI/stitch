# stitch-client

Async shared client utilities for calling the Stitch API from internal services.

## Downstream auth (Auth0 M2M)

Build the client with `AsyncStitchClient.from_service_env(api_base_url=...)`. The
auth mode is selected by the environment:

- **`STITCH_AUTH_CLIENT_ID` / `_CLIENT_SECRET` / `_AUDIENCE` / `_ISSUER_URL` all
  set** → Auth0 client-credentials (M2M): short-lived tokens are fetched on
  demand, cached in memory, and re-fetched reactively on a 401.
- **all four absent** → no `Authorization` header (the local `AUTH_DISABLED`
  path; fails loud with 401 against a real API).
- **partially set** → raises `StitchAuthError` (a half-config is a typo).

Call `await validate_downstream_auth_at_startup(api_base_url=...)` in your
service startup to fail fast on bad credentials.

`from_service_env` keeps your service's own base-url variable — it does not read
`STITCH_API_BASE_URL`.

See `deployments/AUTH.md` for the full topology, tenant setup, and
troubleshooting.
