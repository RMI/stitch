import { useMemo, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useQueryClient } from "@tanstack/react-query";
import { FieldCard } from "./FieldCard";
import Button from "./Button";
import { useFieldSourceValues } from "../hooks/useResources";
import { useHasPermission } from "../hooks/usePermissions";
import { useConfig } from "../config/useConfig";
import { createAuthenticatedFetcher } from "../auth/api";
import { updateFieldSourcePriority } from "../queries/api";
import { resourceKeys } from "../queries/resources";
import {
  SOURCE_COLORS,
  SOURCE_LABELS,
  UNKNOWN_SOURCE_LABEL,
  DEFAULT_FIELD_COLOR,
} from "../constants/sourceMeta";

const RESOURCE_WRITE = "resource:write";

function arraysEqual(a, b) {
  return a.length === b.length && a.every((value, index) => value === b[index]);
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

function FieldSourcesPanel({
  isLoading,
  isError,
  sources,
  endpoint,
  resourceId,
  fieldKey,
}) {
  const canEdit = useHasPermission(RESOURCE_WRITE);
  const config = useConfig();
  const { getAccessTokenSilently } = useAuth0();
  const queryClient = useQueryClient();

  const [isEditing, setIsEditing] = useState(false);
  const [workingOrder, setWorkingOrder] = useState([]);
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

  // Nothing to reorder with fewer than two sources.
  const canReorder = canEdit && sources.length > 1;
  const changed = isEditing && !arraysEqual(workingOrder, originalOrder);

  function beginEdit() {
    setWorkingOrder(originalOrder);
    setSaveError("");
    setIsEditing(true);
  }

  function cancelEdit() {
    setIsEditing(false);
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

  async function handleSave() {
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
      setIsEditing(false);
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
        {canReorder && !isEditing && (
          <Button variant="ghost" className="px-2 py-1" onClick={beginEdit}>
            Edit
          </Button>
        )}
        {isEditing && (
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              className="px-2 py-1"
              onClick={cancelEdit}
              disabled={isSaving}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              className="px-2 py-1"
              onClick={handleSave}
              disabled={!changed || isSaving}
            >
              {isSaving ? "Saving…" : "Save"}
            </Button>
          </div>
        )}
      </div>
      {saveError && <p className="text-sm text-danger">{saveError}</p>}
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
                isEditing ? (
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
