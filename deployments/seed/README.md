# Stitch Seed container

This package/deployment is intended to add fake data to a running stitch
instance, for demonstration and testing purposes

It also serves as a base/starting point of an ETL container, since this handles
model validation and POSTing Oil and Gas fields to the application.

It reads static seed JSON files from `data`, and also generates objects for
posting with `Faker`

Downstream Stitch API auth uses Auth0 M2M (client-credentials) via
`stitch-client`: set `STITCH_AUTH_CLIENT_ID` / `_CLIENT_SECRET` / `_AUDIENCE` /
`_ISSUER_URL`, or leave them unset to run against a local `AUTH_DISABLED` API
with no `Authorization` header. See `deployments/AUTH.md`.
