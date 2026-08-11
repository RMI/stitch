import { useState } from "react";
import { FieldCard } from "./FieldCard";
import Button from "./Button";
import Input from "./Input";
import {
  useCreateSourceForResource,
  useFieldSourceValues,
} from "../hooks/useResources";
import { useHasPermission } from "../hooks/usePermissions";
import {
  SOURCE_COLORS,
  SOURCE_LABELS,
  UNKNOWN_SOURCE_LABEL,
  DEFAULT_FIELD_COLOR,
} from "../constants/sourceMeta";

// Build a bare "User Generated" (rmi) source that populates only `fieldKey`, to
// be created and attached to the resource. `name`/`country` are required-present
// keys on the field model (null unless the panel's field IS name/country — the
// [fieldKey] spread then overrides the null). The curator's note and an audit
// breadcrumb ride along in `source_record.payload`.
function buildRmiSourcePayload({ fieldKey, value, note }) {
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
      payload: { action: "field_overwrite", field: fieldKey, value, note },
    },
  };
}

function SourceValueRow({ source, value, sourceId, isWinner }) {
  const barColor = SOURCE_COLORS[source] ?? DEFAULT_FIELD_COLOR;
  const sourceLabel = SOURCE_LABELS[source] ?? UNKNOWN_SOURCE_LABEL;
  const meta =
    sourceId !== null && sourceId !== undefined
      ? `${sourceLabel} · #${sourceId}`
      : sourceLabel;
  // Quote strings to set text values apart; render numbers/booleans bare.
  const display = typeof value === "string" ? `"${value}"` : String(value);

  return (
    <div
      className={`rounded-md border border-line border-l-4 px-2.5 py-1.5 ${
        isWinner ? "bg-surface" : "bg-panel"
      }`}
      style={{ borderLeftColor: barColor }}
    >
      <div className="break-words text-sm text-ink">{display}</div>
      <div className="mt-0.5 text-xs text-ink-muted">{meta}</div>
    </div>
  );
}

// The value entry form, revealed after the curator clicks "+". Lets them enter a
// new "User Generated" value (with an optional note) for this field; on Save it
// creates and attaches an rmi source to the resource.
function AddSourceForm({ endpoint, resourceId, fieldKey, onSaved }) {
  const createSource = useCreateSourceForResource(endpoint);

  const [value, setValue] = useState("");
  const [note, setNote] = useState("");

  const trimmedValue = value.trim();
  const isSaving = createSource.isPending;
  const saveError = createSource.error
    ? createSource.error.message || "Failed to add value."
    : "";

  async function handleSave() {
    if (!trimmedValue || isSaving) return;

    const payload = buildRmiSourcePayload({
      fieldKey,
      value: trimmedValue,
      note: note.trim() || null,
    });

    try {
      // Resolves after the mutation's cache invalidation, so the refreshed
      // data is on its way before the form closes.
      await createSource.mutateAsync({ resourceId, payload });
      onSaved();
    } catch {
      // Surfaced via `createSource.error` above; the form stays mounted with
      // the draft intact so the curator can retry.
    }
  }

  return (
    <div className="space-y-2 rounded-md border border-line bg-surface p-2">
      <Input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="New value"
        aria-label="New value"
        className="w-full"
      />
      <Input
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="Note (optional)"
        aria-label="Note"
        className="w-full"
      />
      <div className="flex items-center gap-2">
        <Button
          variant="primary"
          onClick={handleSave}
          disabled={!trimmedValue || isSaving}
        >
          {isSaving ? "Saving…" : "Save"}
        </Button>
      </div>
      {saveError && <p className="text-sm text-danger">{saveError}</p>}
    </div>
  );
}

function FieldSourcesPanel({
  isLoading,
  isError,
  sources,
  canEdit,
  endpoint,
  resourceId,
  fieldKey,
}) {
  const [isEditing, setIsEditing] = useState(false);
  // Keep the value form hidden until the curator clicks "+", to reduce clutter.
  const [isAdding, setIsAdding] = useState(false);

  function stopEditing() {
    setIsEditing(false);
    setIsAdding(false);
  }

  return (
    <div className="mt-2 space-y-2 rounded-md border border-line bg-panel p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          All sources
        </p>
        {canEdit &&
          (isEditing ? (
            <Button variant="ghost" onClick={stopEditing}>
              Cancel
            </Button>
          ) : (
            <Button variant="ghost" onClick={() => setIsEditing(true)}>
              Edit
            </Button>
          ))}
      </div>
      {isEditing &&
        (isAdding ? (
          <AddSourceForm
            endpoint={endpoint}
            resourceId={resourceId}
            fieldKey={fieldKey}
            onSaved={stopEditing}
          />
        ) : (
          <Button
            variant="secondary"
            onClick={() => setIsAdding(true)}
            aria-label="Add value"
          >
            +
          </Button>
        ))}
      {isLoading && <p className="text-sm text-ink-muted">Loading sources…</p>}
      {isError && (
        <p className="text-sm text-danger">Failed to load source values.</p>
      )}
      {!isLoading && !isError && sources.length === 0 && (
        <p className="text-sm text-ink-muted">
          No source values for this field.
        </p>
      )}
      {!isLoading && !isError && sources.length > 0 && (
        <div className="space-y-1.5">
          {/* The endpoint returns best-priority first, so index 0 is the winner. */}
          {sources.map((row, idx) => (
            <SourceValueRow
              key={`${row.source}-${row.source_id}`}
              source={row.source}
              value={row.value}
              sourceId={row.source_id}
              isWinner={idx === 0}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// A FieldCard for the resource detail page: clicking a populated value lazily
// fetches every source's value for that field and shows them in priority order.
// Curators (source:write + resource:write) can also expand a field that has no
// values yet, to add the first one.
export default function ResourceFieldCard({
  endpoint,
  resourceId,
  fieldKey,
  label,
  value,
  source,
}) {
  const [isOpen, setIsOpen] = useState(false);
  // Creating + attaching a source needs both writes, matching
  // POST /oil-gas-fields/{id}/sources. Call both hooks unconditionally.
  const canWriteSource = useHasPermission("source:write");
  const canWriteResource = useHasPermission("resource:write");
  const canEdit = canWriteSource && canWriteResource;

  const hasValue = value !== null && value !== undefined && value !== "";
  // Editors can also open empty fields to add the first value.
  const expandable = hasValue || canEdit;
  const { data, isLoading, isError } = useFieldSourceValues(
    endpoint,
    resourceId,
    fieldKey,
    isOpen && expandable,
  );

  return (
    <FieldCard
      label={label}
      value={value}
      source={source}
      expandable={expandable}
      isOpen={isOpen}
      onToggle={() => setIsOpen((current) => !current)}
    >
      <FieldSourcesPanel
        isLoading={isLoading}
        isError={isError}
        sources={data ?? []}
        canEdit={canEdit}
        endpoint={endpoint}
        resourceId={resourceId}
        fieldKey={fieldKey}
      />
    </FieldCard>
  );
}
