import { useMemo, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useQueryClient } from "@tanstack/react-query";
import { FieldCard } from "./FieldCard";
import Button from "./Button";
import Input from "./Input";
import {
  useCreateSourceForResource,
  useFieldSourceValues,
} from "../hooks/useResources";
import {
  useHasPermission,
  useHasAllPermissions,
} from "../hooks/usePermissions";
import { useConfig } from "../config/useConfig";
import { createAuthenticatedFetcher } from "../auth/api";
import { updateFieldSourcePriority } from "../queries/api";
import { resourceKeys } from "../queries/resources";
import {
  SOURCES,
  SOURCE_COLORS,
  SOURCE_LABELS,
  UNKNOWN_SOURCE_LABEL,
  DEFAULT_FIELD_COLOR,
} from "../constants/sourceMeta";

const RESOURCE_WRITE = "resource:write";
// Reordering rewrites the whole per-field override set, so the API requires read
// access to every source (not just this resource's) on top of resource:write.
// Gate the affordance the same way so it only appears to curators who can save.
const ALL_SOURCE_READ_PERMISSIONS = SOURCES.map(
  (source) => `source:read:${source}`,
);

function arraysEqual(a, b) {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

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

function SourceValueRow({
  source,
  value,
  sourceId,
  isWinner,
  isOverride,
  editControls,
}) {
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
      className={`flex items-center gap-2 rounded-md border border-line border-l-4 px-2.5 py-1.5 ${
        isWinner ? "bg-surface" : "bg-panel"
      }`}
      style={{ borderLeftColor: barColor }}
    >
      <div className="min-w-0 flex-1">
        <div className="break-words text-sm text-ink">{display}</div>
        <div className="mt-0.5 text-xs text-ink-muted">
          {meta}
          {isOverride && (
            <span className="ml-1.5 rounded bg-rmiblue-100 px-1 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-bluespruce">
              curated
            </span>
          )}
        </div>
      </div>
      {editControls}
    </div>
  );
}

function MoveButtons({ onMoveUp, onMoveDown, canMoveUp, canMoveDown, label }) {
  return (
    <div className="flex flex-col gap-0.5">
      <button
        type="button"
        onClick={onMoveUp}
        disabled={!canMoveUp}
        aria-label={`Move ${label} up`}
        className="rounded border border-line px-1.5 text-xs leading-4 text-ink-muted hover:bg-rmiblue-100 disabled:cursor-not-allowed disabled:opacity-40"
      >
        ↑
      </button>
      <button
        type="button"
        onClick={onMoveDown}
        disabled={!canMoveDown}
        aria-label={`Move ${label} down`}
        className="rounded border border-line px-1.5 text-xs leading-4 text-ink-muted hover:bg-rmiblue-100 disabled:cursor-not-allowed disabled:opacity-40"
      >
        ↓
      </button>
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
  const canWriteResource = useHasPermission(RESOURCE_WRITE);
  const canReadAllSources = useHasAllPermissions(ALL_SOURCE_READ_PERMISSIONS);
  const config = useConfig();
  const { getAccessTokenSilently } = useAuth0();
  const queryClient = useQueryClient();

  const [isEditing, setIsEditing] = useState(false);
  // Keep the value form hidden until the curator clicks "+", to reduce clutter.
  const [isAdding, setIsAdding] = useState(false);
  const [workingOrder, setWorkingOrder] = useState([]);
  // The order captured when editing began. `orderChanged` and the stale-panel
  // check both compare against this snapshot -- not the live `originalOrder` --
  // so a background refetch can't be mistaken for a user edit.
  const [baselineOrder, setBaselineOrder] = useState([]);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const originalOrder = useMemo(
    () => sources.map((row) => row.source_id),
    [sources],
  );
  const sourcesById = useMemo(
    () => new Map(sources.map((row) => [row.source_id, row])),
    [sources],
  );

  // Reordering needs resource:write, read access to every source (so the save
  // acts on a complete picture -- see the priority route), and at least two
  // sources to swap.
  const canReorder =
    canWriteResource && canReadAllSources && sources.length > 1;
  // The Edit affordance opens the shared edit mode for either capability:
  // reordering the existing sources or adding a new value.
  const canEnterEdit = canReorder || canEdit;
  // Did the curator actually reorder? Compared against the edit-start snapshot, so
  // a background refetch shifting `originalOrder` can't spuriously enable Save.
  const orderChanged = isEditing && !arraysEqual(workingOrder, baselineOrder);
  // Did the underlying sources diverge from what the curator started editing --
  // an added/removed source, or someone else's re-order of the same set? Either
  // way the working order is stale and a save would overwrite newer state, so
  // surface a notice and block it until the curator re-opens from the fresh list.
  const sourcesChanged =
    isEditing && !arraysEqual(baselineOrder, originalOrder);

  function beginEdit() {
    setWorkingOrder(originalOrder);
    setBaselineOrder(originalOrder);
    setSaveError("");
    setIsEditing(true);
  }

  function stopEditing() {
    setIsEditing(false);
    setIsAdding(false);
    setSaveError("");
  }

  function move(index, delta) {
    setWorkingOrder((current) => {
      const target = index + delta;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  async function handleSaveOrder() {
    setIsSaving(true);
    setSaveError("");
    try {
      const fetcher = createAuthenticatedFetcher(
        config,
        getAccessTokenSilently,
      );
      await updateFieldSourcePriority(
        config,
        resourceId,
        fieldKey,
        workingOrder,
        fetcher,
        endpoint,
      );
      // Refresh both the per-field ranking and the resource detail (its coalesced
      // winner / collapsed value may have changed).
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: resourceKeys.fieldSources(endpoint, resourceId, fieldKey),
        }),
        queryClient.invalidateQueries({
          queryKey: resourceKeys.detail(endpoint, resourceId),
        }),
      ]);
      stopEditing();
    } catch (err) {
      setSaveError(err.message || "Failed to save source order.");
    } finally {
      setIsSaving(false);
    }
  }

  const displayRows = isEditing
    ? workingOrder.map((id) => sourcesById.get(id)).filter(Boolean)
    : sources;

  return (
    <div className="mt-2 space-y-2 rounded-md border border-line bg-panel p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          All sources
        </p>
        {!isEditing && canEnterEdit && (
          <Button variant="ghost" className="px-2 py-1" onClick={beginEdit}>
            Edit
          </Button>
        )}
        {isEditing && (
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              className="px-2 py-1"
              onClick={stopEditing}
              disabled={isSaving}
            >
              Cancel
            </Button>
            {canReorder && (
              <Button
                variant="primary"
                className="px-2 py-1"
                onClick={handleSaveOrder}
                disabled={!orderChanged || isSaving || sourcesChanged}
              >
                {isSaving ? "Saving…" : "Save"}
              </Button>
            )}
          </div>
        )}
      </div>
      {saveError && <p className="text-sm text-danger">{saveError}</p>}
      {sourcesChanged && (
        <p className="text-sm text-warning">
          The source list changed. Cancel and re-open to edit the current order.
        </p>
      )}
      {isEditing &&
        canEdit &&
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
          {/* Index 0 is the winner in both read (best-first from the API) and edit
              (top of the working order) modes. */}
          {displayRows.map((row, idx) => (
            <SourceValueRow
              key={`${row.source}-${row.source_id}`}
              source={row.source}
              value={row.value}
              sourceId={row.source_id}
              isWinner={idx === 0}
              isOverride={!isEditing && row.is_override}
              editControls={
                isEditing && canReorder ? (
                  <MoveButtons
                    label={SOURCE_LABELS[row.source] ?? UNKNOWN_SOURCE_LABEL}
                    canMoveUp={idx > 0}
                    canMoveDown={idx < displayRows.length - 1}
                    onMoveUp={() => move(idx, -1)}
                    onMoveDown={() => move(idx, 1)}
                  />
                ) : null
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

// A FieldCard for the resource detail page: clicking a populated value lazily
// fetches every source's value for that field and shows them in priority order.
// With `resource:write`, the panel also allows reordering sources for the field.
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
