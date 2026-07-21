# stitch-llm

FastAPI companion service for generating validated LLM suggestions for missing
Stitch oil and gas field values.

The service calls the Stitch API through `stitch-client` and calls the Azure
OpenAI Responses API for structured field suggestions.

Downstream Stitch API auth uses Auth0 M2M (client-credentials): set
`STITCH_AUTH_CLIENT_ID` / `_CLIENT_SECRET` / `_AUDIENCE` / `_ISSUER_URL`, or
leave them unset to run against a local `AUTH_DISABLED` API with no
`Authorization` header. `/health/details` reports the derived `auth_mode`. See
`deployments/AUTH.md`.
