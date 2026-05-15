# Seed `SourceRecord` on Base `Source`

## Summary
Implement `SourceRecord` as an optional field on `stitch.models.Source`, persist it for Seed-created sources, and keep normal read responses unchanged by exposing it only from a dedicated source detail endpoint. This supersedes PR `#95`’s split create/detail source types: the domain model carries the field, while API/view layers decide when to serialize it.

## Key Changes
- Add `SourceRecord` to `packages/stitch-models` with:
  - `record_id: str | None = None`
  - `run_id: str | None = None`
  - `observed_at: datetime`
  - `producer: str`
  - `payload: JsonValue`
- Extend `Source[...]` in `packages/stitch-models/src/stitch/models/__init__.py` with:
  - `source_record: SourceRecord | None = None`
- Update OGSI source unions in `packages/stitch-ogsi` so all source variants inherit the new base field automatically.
- Keep existing list/plain read contracts unchanged:
  - `/oil-gas-fields/` unchanged
  - `/oil-gas-fields/{id}` unchanged
  - `/oil-gas-field-sources/` unchanged
  - `/oil-gas-field-sources/{id}` unchanged
- Add a dedicated source detail response for reads that should include the record:
  - `GET /oil-gas-field-sources/{id}/detail` returns the full source including `source_record`
- Update API persistence for oil-and-gas sources:
  - add a JSON column for `source_record` to `OilGasFieldSourceModel`
  - ensure `create_from_entity` persists it from the base source model
  - ensure normal `as_entity()` behavior used by existing read paths excludes it from default source responses
  - add a detail conversion path used only by the new source detail endpoint
- Seed service changes:
  - when building faker payloads, attach a generated `source_record` to each source row
  - when loading static payloads, attach a generated `source_record` to each source row
  - reject any input payload whose source already includes `source_record`
  - `source_record.payload` must be the exact original source dict before Seed adds `source_record`
  - Seed-generated metadata policy:
    - `run_id`: one generated id per seed run
    - `observed_at`: timestamp when each source row is processed
    - `producer`: fixed seed identifier/version string
    - `record_id`: derived from static file path + item index, or faker row index for generated data
- Update `packages/stitch-client` only if needed to support the new source detail endpoint or stricter create payload validation.

## Test Plan
- `stitch-models`
  - validate `SourceRecord`
  - verify `Source` subclasses accept `source_record`
  - verify existing source/resource validation still passes when `source_record` is omitted
- `stitch-ogsi`
  - verify discriminated source parsing still works with `source_record`
  - verify source variants preserve `source_record` when present
- API/db
  - creating a source/resource from Seed-shaped payload persists `source_record`
  - normal source GET/list responses do not include `source_record`
  - `GET /oil-gas-field-sources/{id}/detail` includes `source_record`
  - licensed-source filtering still applies to the new detail endpoint
- Seed
  - faker payloads include generated `source_record`
  - static payloads include generated `source_record`
  - `payload` equals the original source dict, not the mutated dict with `source_record`
  - seeding fails fast if an input source already contains `source_record`

## Assumptions
- This first pass is Seed-only for creation behavior; no LLM, ETL, or frontend authoring flow is added.
- `source_record` is not added to resource detail responses in this phase.
- The API remains snake_case, so the field is `source_record`.
- No `source_record_hash` is added in this phase unless implementation uncovers a hard persistence need; the requested behavior does not require it.
