# Resource-state read model

The oil & gas field **list** and **filter-options** endpoints work out every
field's winning value on each request, which takes ~2–3 s at ~50K resources. The
read model is a precomputed table, `og_field_resource_state`, that those
endpoints can read instead.

The table is a cache, not a source of truth. Everything in it can be rebuilt from
the authoritative tables at any time, and when it can't be trusted the API simply
answers the slower way ("live"), with the same results.

So far only the tables exist: they start empty and not ready, and nothing writes
or reads them yet, so answers are unchanged.

## How it works

- **What's stored:** one row per resource *per permission profile*, holding each
  field's winning value and which source it came from (`provenance`). There are
  four profiles: all public sources, plus any combination of the two restricted
  sources (`wm`, `ccr`). See `db/read_model/permissions.py`. Only a request
  whose licensed sources *exactly* match one of the four profiles can be served
  from the table; everyone else gets the live answer.
- **Readiness:** a single row in `og_field_resource_state_status`. Only a complete
  full rebuild sets `ready = true`, recording the commit of the code that ran it
  (`code_version`). Each row also records the commit that computed it. The table
  may be used only when it is ready **and** was built by the same commit the API
  is running.

## Changing the code safely

- **New field** on `OilGasFieldBase`: add the column to `OGFieldResourceState`
  (an import-time check fails until you do) plus a migration.
- **New source key:** decide whether it's public or restricted in
  `db/read_model/permissions.py`. A test fails until you do; until then, anyone
  holding the new key would get the live path.
