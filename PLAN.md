# STIT-495 — RMI_CUSTOM field overwrite action from Resource Detail

## Context

**Ticket (via `acli`):** STIT-495 — *"Add RMI_CUSTOM field overwrite action from Resource Detail"* (Story, Selected for Development).

> Add an edit action for fields where a user needs to enter a new curated value that does not
> exactly match an existing source value.

**Acceptance criteria:**
1. Field card exposes an overwrite/edit action for permitted users.
2. User can enter a new value and required/optional notes *per decision*.
3. Value is validated against field schema.
4. Override is stored as `RMI_CUSTOM` or equivalent custom source state.
5. Original source values remain unchanged and visible.
6. Override becomes the winning value according to coalescing rules.
7. Audit trail records all overwrite details.

Branch `feat/rmi-write` builds on **PR #191** (`feat/direct-source-creation`, in review), which added
`POST /api/v1/oil-gas-fields/{id}/sources` — creates a bare source and attaches it to a resource.
In this codebase the "equivalent custom source state" (AC #4) is the existing **`rmi`** source key,
labelled **"User Generated"** (`constants/sourceMeta.js`). No new source type is required.

The UX reuses **PR #174**'s (`feat/re-prioritize-field`) per-panel **Edit** toggle. PR #174's code is
**not** in this branch (different base), so its edit-toggle pattern is **replicated here**, not imported.

## Scope for this pass (per your direction)

**In scope now** — AC #1, #2, #4, #5, #7, and (partially) #3:
- Per-field Edit toggle revealing a **value text field + notes field + "+"** at the top of the field's source panel.
- Submitting creates one **`rmi`** source whose only populated field is that panel's field, attached
  to the resource. Other sources are untouched and stay visible (AC #5).
- **Notes** are stored in the source's `source_record.payload` JSON (AC #2) and are **shown in the
  source-detail view** (AC #7).
- Basic validation via backend field schema (AC #3, see edge cases).

**Decision to confirm:** notes default to **optional** (do not block submit). Say the word if a note
should be **required** for every override.

**Explicitly deferred** (flag to product; not built in this pass):
- **AC #6 — override becomes the winning value.** You asked to not set priority yet. Creating an
  `rmi` source does **not** by itself guarantee it wins coalescing. This AC is **not** satisfied by
  this pass; it needs the priority work (the `og_field_source_priority` model + PR #174's
  `updateFieldSourcePriority`) to follow.

I want to confirm this in-scope/deferred split before implementing, since AC #6 is central to the
ticket but conflicts with "don't worry about priority."

## Success criteria (this pass)

1. Expanding a populated field card shows its "All sources" panel with an **Edit** button, but only for users with `source:write` **and** `resource:write`.
2. Clicking **Edit** reveals a text input + **"+"** at the top of the panel, plus a way to exit.
3. Entering a value (+ optional note) and **"+"** issues `POST /oil-gas-fields/{id}/sources` with `source: "rmi"`, only this panel's field populated, and the note in `source_record.payload`.
4. On success: this field's source list and the resource detail refresh; the new "User Generated" row appears; existing source rows are unchanged.
5. The note is visible when viewing that source's details in the resource Sources section.
6. Validation/other errors surface inline and preserve the draft.
7. No Edit button for users without the permissions.

## Approach

Two files change:
**`deployments/stitch-frontend/src/components/ResourceFieldCard.jsx`** (the overwrite control) and
**`deployments/stitch-frontend/src/pages/ResourceDetailPage.jsx`** (`SourceRow`, to display the note).

### A. Overwrite control — `ResourceFieldCard.jsx`

1. **Thread context into `FieldSourcesPanel`.** `ResourceFieldCard` already has `endpoint`,
   `resourceId`, `fieldKey`; it currently passes only `isLoading/isError/sources`. Also pass
   `endpoint`, `resourceId`, `fieldKey`.

2. **Replicate PR #174's edit-toggle (panel-local state, no shared store).** In `FieldSourcesPanel`:
   - `canEdit = useHasPermission("source:write") && useHasPermission("resource:write")`
     (reuse `../hooks/usePermissions`, already in-branch).
   - `useState`: `isEditing`, `draft` (value), `note`, `isSaving`, `saveError`.
   - Edit / Cancel ghost `Button`s in the panel header beside the "All sources" label (the existing
     header comment already reserves this spot).

3. **Add-row (only when `isEditing`), at the top of the list:** reuse `../components/Input` for the
   **value** field and a second `Input` (or textarea) for the **note**, plus `../components/Button`
   ("+") to submit. Submit disabled when `draft` (value) is empty or `isSaving`. The note is optional
   (see Decision above).

4. **Create call.** Add a local payload builder mirroring `buildLLMSourcePayload`
   (`ResourceDetailPage.jsx`), recording the note + audit details in `source_record.payload` (AC #2, #7):
   ```js
   function buildRmiSourcePayload({ fieldKey, value, note }) {
     // name/country are required-present keys on the field model; the [fieldKey]
     // spread overrides them when the panel's field IS name or country.
     return {
       source: "rmi",
       name: null,
       country: null,
       [fieldKey]: value,
       source_record: {
         record_id: null,
         run_id: null,
         observed_at: new Date().toISOString(),
         producer: "stitch-frontend",
         payload: { action: "field_overwrite", field: fieldKey, value, note: note || null },
       },
     };
   }
   ```
   Call `createSourceForResource(config, resourceId, payload, fetcher, endpoint)` (existing,
   `queries/api.js:136`) with `createAuthenticatedFetcher(config, getAccessTokenSilently)`.

5. **Refresh after success** via `useQueryClient()` — invalidate:
   - `resourceKeys.fieldSources(endpoint, resourceId, fieldKey)` (this panel), and
   - `resourceKeys.detail(endpoint, resourceId)` (coalesced value / provenance / Sources section).
   Both factories exist in `queries/resources.js`. On success clear `draft` and exit edit mode;
   on error set `saveError`, keep the draft.

**Reused, unchanged:** `createSourceForResource`, `usePermissions`, `Button`, `Input`,
`resourceKeys`, `SOURCE_LABELS.rmi = "User Generated"`. **No backend changes** — endpoint ships in PR #191.

### B. Show the note in source details — `ResourceDetailPage.jsx`

`SourceRow`'s expanded view (`ResourceDetailPage.jsx:474`) already fetches the source detail
(`useSourceDetail`) and renders `sourceRecord` fields plus a `TechnicalImportRecord` (raw payload).
Add a **"Note"** display: when `sourceRecord.payload?.note` is present, render it as a `FieldCard`
(or a short labelled block) in the existing `FieldGrid` alongside Producer / Observed at. This makes
the override note human-visible without expanding the raw JSON (which still shows it verbatim). No
change to `SourcesSection` itself.

## Edge cases / decisions

- **AC #3 validation:** the input yields a string; numeric fields (latitude, longitude, `*_year`)
  rely on backend Pydantic coercion ("1998" → 1998), with invalid input surfaced via `saveError`.
  This covers "validated against field schema" server-side; no duplicate client schema.
- **Array fields not affected:** `owners`/`operators` render via `OrganizationsSection`, not
  `ResourceFieldCard`, so no array/object input is ever needed here.
- **Empty fields:** a field card is only expandable when it already has a value, so the overwrite
  control is unavailable for currently-empty fields. Matches existing behavior; flag if adding-to-empty is wanted.
- **`name`/`country` fields:** the `[fieldKey]: value` spread intentionally overrides the null defaults.

## Verification

- **Unit tests** — extend `deployments/stitch-frontend/src/components/ResourceFieldCard.test.jsx` (vitest + RTL):
  - Edit button hidden without permissions, shown with both.
  - Toggle Edit reveals value + note inputs + "+"; Cancel hides them.
  - Submit calls `createSourceForResource` with the expected payload (`source: "rmi"`, only
    `fieldKey` populated, note + audit in `source_record.payload`) and invalidates the two query keys.
  - Backend error → `saveError` shown, draft preserved.
  - `SourceRow` (in `ResourceDetailPage.test.jsx`, if present) renders the note when
    `payload.note` is set.
  Run: `npm test` (or `npx vitest run`) in `deployments/stitch-frontend`.
- **Lint/format:** `npm run lint` / prettier in `deployments/stitch-frontend`.
- **Manual (API with PR #191):** as a curator, open a resource, expand a populated field, Edit →
  type value + note → "+", confirm a new "User Generated" source row appears and coalesced
  value/provenance refresh; open that source's details and confirm the note is visible; confirm
  existing sources are unchanged and the control is absent for non-privileged users.
