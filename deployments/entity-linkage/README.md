# entity-linkage

Basic Entity linkage service.

Currently matches on exact name and country.
Invoked through the `/start` endpoint in the `entity-linkage` service.

Downstream Stitch API auth uses Auth0 M2M (client-credentials) via
`stitch-client`: set `STITCH_AUTH_CLIENT_ID` / `_CLIENT_SECRET` / `_AUDIENCE` /
`_ISSUER_URL`, or leave them unset to run against a local `AUTH_DISABLED` API
with no `Authorization` header. `/health/details` reports the derived
`auth_mode`. See `deployments/AUTH.md`.
