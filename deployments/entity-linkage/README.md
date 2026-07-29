# entity-linkage

Basic Entity linkage service.

Matches resources on normalized (case-insensitive, whitespace-trimmed) name and
country, and proposes them to the Stitch API as merge candidates.

## Endpoints

- `POST /api/v1/oil-gas-fields/{id}/link` — link a single resource against its
  duplicates in bounded memory: fetch its detail, search the API for same-name
  candidates, confirm same country, and (when `apply_merges` is true) submit the
  merge candidate. This is the unit of work the bulk pass iterates.
- `POST /api/v1/oil-gas-fields/link` — run the same bounded matcher over every
  resource, streaming the list one page at a time. Replaces the in-memory
  `/start` pass for production-scale datasets. Still runs synchronously in the
  request (it fixes memory, not wall-time).
- `POST /api/v1/start` — the original whole-dataset in-memory pass. Superseded by
  the bounded endpoints above and retained for now; it loads every resource into
  memory and fails at production scale.

All linkage endpoints require the `service:entity-linkage:run` permission and
default to a dry run (`apply_merges` defaults to `false`).

Downstream Stitch API auth is provided through `STITCH_CLIENT_BEARER_TOKEN`.
