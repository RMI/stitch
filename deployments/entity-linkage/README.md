# entity-linkage (deployment)

A small client container that:
1) makes a GET request to the Stitch API
2) makes a POST request to the Stitch API

Note that for now, it does not terminate (runs in loop looking for resources to
merge)

## Configuration

- `API_URL` (required)
  - Example: `http://api:8000`
- `ENTITY_LINKAGE_SLEEP_SECONDS` (default: `10`)
- `ENTITY_LINKAGE_TIMEOUT_SECONDS` (default: `10`)
- `ENTITY_LINKAGE_MAX_RETRIES` (default: `60`)
- `ENTITY_LINKAGE_RETRY_BACKOFF_SECONDS` (default: `1`)
- `ENTITY_LINKAGE_LOG_LEVEL` (default: `INFO`)
