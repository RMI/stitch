import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useQueryClient } from "@tanstack/react-query";
import { FieldCard } from "./FieldCard";
import Button from "./Button";
import Input from "./Input";
import { useFieldSourceValues } from "../hooks/useResources";
import { useHasPermission } from "../hooks/usePermissions";
import { createAuthenticatedFetcher } from "../auth/api";
import { useConfig } from "../config/useConfig";
import { createSourceForResource } from "../queries/api";
import { resourceKeys } from "../queries/resources";
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

// The add-a-value form shown at the top of the panel while editing. Lets a
// curator enter a new "User Generated" value (with an optional note) for this
// field; on submit it creates and attaches an rmi source to the resource.
function AddSourceForm({ endpoint, resourceId, fieldKey, onAdded }) {
  const config = useConfig();
  const { getAccessTokenSilently } = useAuth0();
  const queryClient = useQueryClient();

  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const trimmedValue = value.trim();

  async function handleAdd() {
    if (!trimmedValue || isSaving) return;
    setIsSaving(true);
    setSaveError("");

    const fetcher = createAuthenticatedFetcher(config, getAccessTokenSilently);
    const payload = buildRmiSourcePayload({
      fieldKey,
      value: trimmedValue,
      note: note.trim() || null,
    });

    try {
      await createSourceForResource(
        config,
        resourceId,
        payload,
        fetcher,
        endpoint,
      );
      // Refresh this field's source list and the resource detail (coalesced
      // value / provenance / Sources section) so the new value shows at once.
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: resourceKeys.fieldSources(endpoint, resourceId, fieldKey),
        }),
        queryClient.invalidateQueries({
          queryKey: resourceKeys.detail(endpoint, resourceId),
        }),
      ]);
      onAdded();
    } catch (err) {
      setSaveError(err.message || "Failed to add value.");
    } finally {
      setIsSaving(false);
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
          onClick={handleAdd}
          disabled={!trimmedValue || isSaving}
          aria-label="Add value"
        >
          {isSaving ? "Adding…" : "+"}
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
  endpoint,
  resourceId,
  fieldKey,
}) {
  // Creating + attaching a source needs both the source and resource writes,
  // matching POST /oil-gas-fields/{id}/sources. Call both hooks unconditionally.
  const canWriteSource = useHasPermission("source:write");
  const canWriteResource = useHasPermission("resource:write");
  const canEdit = canWriteSource && canWriteResource;

  const [isEditing, setIsEditing] = useState(false);

  return (
    <div className="mt-2 space-y-2 rounded-md border border-line bg-panel p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          All sources
        </p>
        {canEdit &&
          (isEditing ? (
            <Button variant="ghost" onClick={() => setIsEditing(false)}>
              Cancel
            </Button>
          ) : (
            <Button variant="ghost" onClick={() => setIsEditing(true)}>
              Edit
            </Button>
          ))}
      </div>
      {isEditing && (
        <AddSourceForm
          endpoint={endpoint}
          resourceId={resourceId}
          fieldKey={fieldKey}
          onAdded={() => setIsEditing(false)}
        />
      )}
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
export default function ResourceFieldCard({
  endpoint,
  resourceId,
  fieldKey,
  label,
  value,
  source,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const expandable = value !== null && value !== undefined && value !== "";
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
        endpoint={endpoint}
        resourceId={resourceId}
        fieldKey={fieldKey}
      />
    </FieldCard>
  );
}
