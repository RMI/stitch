# stitch-client

Async shared client utilities for calling the Stitch API from internal services.

Use `STITCH_CLIENT_BEARER_TOKEN` with
`env_bearer_token_headers_provider()` to send a shared bearer token without
hand-rolling `Authorization` headers in deployment code.
