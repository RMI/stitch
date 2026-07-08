import { useState } from "react";
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

function SourceValueRow({
  source,
  value,
  id,
  isWinner,
  isEditing,
  isFirst,
  isLast,
  onMoveUp,
  onMoveDown,
}) {
  const barColor = SOURCE_COLORS[source] ?? DEFAULT_FIELD_COLOR;
  const sourceLabel = SOURCE_LABELS[source] ?? UNKNOWN_SOURCE_LABEL;
  const meta =
    id !== null && id !== undefined ? `${sourceLabel} · #${id}` : sourceLabel;
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
        <div className="mt-0.5 text-xs text-ink-muted">{meta}</div>
      </div>
      {isEditing && (
        <div className="flex shrink-0 flex-col gap-0.5">
          <button
            type="button"
            aria-label={`Move ${sourceLabel} up`}
            disabled={isFirst}
            onClick={onMoveUp}
            className="rounded border border-line px-1.5 text-xs leading-4 text-ink-muted hover:bg-surface disabled:cursor-not-allowed disabled:opacity-40"
          >
            ▲
          </button>
          <button
            type="button"
            aria-label={`Move ${sourceLabel} down`}
            disabled={isLast}
            onClick={onMoveDown}
            className="rounded border border-line px-1.5 text-xs leading-4 text-ink-muted hover:bg-surface disabled:cursor-not-allowed disabled:opacity-40"
          >
            ▼
          </button>
        </div>
      )}
    </div>
  );
}

function FieldSourcesPanel({
  isLoading,
  isError,
  sources,
  canEdit,
  isEditing,
  onStartEdit,
  onCancelEdit,
  onSave,
  onMove,
  isChanged,
  isSaving,
  saveError,
}) {
  const hasSources = !isLoading && !isError && sources.length > 0;
  // Editing only makes sense when there is more than one source to order.
  const canReorder = canEdit && sources.length > 1;

  return (
    <div className="mt-2 space-y-2 rounded-md border border-line bg-panel p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          All sources
        </p>
        {hasSources && canReorder && !isEditing && (
          <Button
            variant="ghost"
            className="min-h-0 px-2 py-1"
            onClick={onStartEdit}
          >
            Edit
          </Button>
        )}
        {isEditing && (
          <div className="flex items-center gap-1.5">
            <Button
              variant="ghost"
              className="min-h-0 px-2 py-1"
              onClick={onCancelEdit}
              disabled={isSaving}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              className="min-h-0 px-2 py-1"
              onClick={onSave}
              disabled={!isChanged || isSaving}
            >
              {isSaving ? "Saving…" : "Save"}
            </Button>
          </div>
        )}
      </div>
      {isEditing && (
        <p className="text-xs text-ink-muted">
          Reorder sources; the top source wins. Save to apply for everyone.
        </p>
      )}
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
      {hasSources && (
        <div className="space-y-1.5">
          {/* Best-priority first, so index 0 is the winner. */}
          {sources.map((row, idx) => (
            <SourceValueRow
              key={`${row.source}-${row.id}`}
              source={row.source}
              value={row.value}
              id={row.id}
              isWinner={idx === 0}
              isEditing={isEditing}
              isFirst={idx === 0}
              isLast={idx === sources.length - 1}
              onMoveUp={() => onMove(idx, -1)}
              onMoveDown={() => onMove(idx, 1)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function sameOrder(a, b) {
  return a.length === b.length && a.every((row, idx) => row.id === b[idx].id);
}

// A FieldCard for the resource detail page: clicking a populated value lazily
// fetches every source's value for that field and shows them in priority order.
// With `resource:write`, a curator can reorder the sources and persist the order.
export default function ResourceFieldCard({
  endpoint,
  resourceId,
  fieldKey,
  label,
  value,
  source,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [workingOrder, setWorkingOrder] = useState([]);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const expandable = value !== null && value !== undefined && value !== "";
  const canEdit = useHasPermission(RESOURCE_WRITE);
  const config = useConfig();
  const { getAccessTokenSilently } = useAuth0();
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useFieldSourceValues(
    endpoint,
    resourceId,
    fieldKey,
    isOpen && expandable,
  );
  const sources = data ?? [];

  function closePanel() {
    setIsEditing(false);
    setSaveError("");
    setIsOpen((current) => !current);
  }

  function startEdit() {
    setSaveError("");
    setWorkingOrder([...sources]);
    setIsEditing(true);
  }

  function cancelEdit() {
    setIsEditing(false);
    setSaveError("");
  }

  function move(index, delta) {
    const target = index + delta;
    if (target < 0 || target >= workingOrder.length) return;
    setWorkingOrder((current) => {
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  async function save() {
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
        workingOrder.map((row) => row.id),
        fetcher,
        endpoint,
      );
      // Refresh this field's source list and the coalesced detail winner.
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
      setSaveError(err.message || "Failed to save source priority.");
    } finally {
      setIsSaving(false);
    }
  }

  const displayedSources = isEditing ? workingOrder : sources;
  const isChanged = isEditing && !sameOrder(workingOrder, sources);

  return (
    <FieldCard
      label={label}
      value={value}
      source={source}
      expandable={expandable}
      isOpen={isOpen}
      onToggle={closePanel}
    >
      <FieldSourcesPanel
        isLoading={isLoading}
        isError={isError}
        sources={displayedSources}
        canEdit={canEdit}
        isEditing={isEditing}
        onStartEdit={startEdit}
        onCancelEdit={cancelEdit}
        onSave={save}
        onMove={move}
        isChanged={isChanged}
        isSaving={isSaving}
        saveError={saveError}
      />
    </FieldCard>
  );
}
