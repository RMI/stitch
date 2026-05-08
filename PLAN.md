# Standardize Downstream Bearer Auth in `stitch-client`

## Summary
Add a single shared downstream-auth path in `stitch-client` for calls into the Stitch API, centered on `STITCH_CLIENT_BEARER_TOKEN`. Use that same internal env var in `seed`, `entity-linkage`, and `stitch-llm`, with Docker Compose mapping different host-side secrets into it as needed.

This change is outbound-only. It standardizes how those three services authenticate when they call the Stitch API through `stitch-client`; it does not change inbound JWT validation on the public FastAPI endpoints.

## Key Changes
- Extend `AsyncStitchClient` so it supports exactly one outbound auth mechanism at a time:
  - `headers_provider` for explicit/custom callers
  - shared env-token mode using `STITCH_CLIENT_BEARER_TOKEN`
- Enforce mutual exclusivity in the client constructor:
  - if more than one outbound auth source is configured, raise `ValueError`
  - if env-token mode is selected but `STITCH_CLIENT_BEARER_TOKEN` is blank/missing, raise `ValueError`
- Keep the generic `headers_provider` path in the client library so future request-token relay remains possible, but stop using relay in `entity-linkage` for the current deployment wiring.
- Implement the shared bearer-header logic in `packages/stitch-client` and export it as part of the package API so deployment code does not hand-roll `Authorization` header construction.

## Deployment Changes
- `seed`
  - construct `AsyncStitchClient` in env-token mode
  - stop relying on ad hoc downstream auth wiring in deployment code
- `entity-linkage`
  - switch downstream Stitch API calls to env-token mode
  - remove current request-token relay from active use in `StitchApiClient`
  - keep auth-context/request-token extraction code only where still needed for inbound request/user handling, not for downstream client auth
- `stitch-llm`
  - replace `STITCH_LLM_MACHINE_TOKEN` usage with the shared client env-token mode
  - remove the current placeholder-vs-machine-token branching from downstream client auth
- Compose and env wiring
  - inside all three containers, set `STITCH_CLIENT_BEARER_TOKEN`
  - map host-side secrets separately:
    - `seed` and `entity-linkage` get the higher-permission token
    - `stitch-llm` gets the lower-permission token
  - remove `STITCH_LLM_MACHINE_TOKEN` from active config/docs
  - update `.env`, `env.example`, and `docker-compose.local.yml` to show the new mapping clearly

## Test Plan
- `packages/stitch-client/tests`
  - env-token mode sends `Authorization: Bearer <token>`
  - constructor rejects multiple auth mechanisms
  - constructor rejects missing/blank `STITCH_CLIENT_BEARER_TOKEN` when env-token mode is requested
  - existing `headers_provider` behavior still works unchanged
- `deployments/entity-linkage/tests`
  - downstream client uses env token, not request relay
  - misconfiguration with competing downstream auth sources fails fast
- `deployments/stitch-llm/tests`
  - downstream client uses shared env-token mode
  - legacy machine-token path is removed or rejected
- `deployments/seed/tests`
  - `run()` constructs the client in env-token mode and fails fast on missing token
- config/docs smoke checks
  - compose file exposes the shared in-container env var for all three services
  - sample env files document the two host-side token values and their service mapping

## Assumptions
- Exact shared client env var: `STITCH_CLIENT_BEARER_TOKEN`
- One outbound auth mechanism per deployment setup means downstream Stitch API auth only, not inbound service endpoint auth
- Default host-side compose variables should be two separate secrets, one privileged for `seed` + `entity-linkage` and one reduced-scope for `stitch-llm`
- `AUTH_DISABLED=false` is the intended local mode for this work; dev placeholder downstream tokens should no longer be used by these three services once the shared env-token mode is wired
