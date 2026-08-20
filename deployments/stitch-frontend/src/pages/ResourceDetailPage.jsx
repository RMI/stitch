import { useId, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useParams, useNavigate } from "react-router";
import {
  useCreateSourceForResource,
  useResourceDetail,
  useSourceDetail,
} from "../hooks/useResources";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { createAuthenticatedFetcher } from "../auth/api";
import { useConfig } from "../config/useConfig";
import { createLLMSuggestion } from "../queries/api";
import { usePermissions } from "../hooks/usePermissions";
import SourceMixBar from "../components/SourceMixBar";
import SectionHeader from "../components/SectionHeader";
import { FieldCard, FieldGrid } from "../components/FieldCard";
import ResourceFieldCard from "../components/ResourceFieldCard";
import { SOURCE_LABELS } from "../constants/sourceMeta";
import Button from "../components/Button";
import {
  AI_SUGGESTION_FIELDS,
  FIELD_META,
  IDENTITY_FIELDS,
  PRODUCTION_FIELDS,
} from "../constants/fieldMeta";

const LLM_AUDIT_PRODUCER = "stitch-frontend";

const OBSERVED_AT_FORMATTER = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "short",
  day: "numeric",
});

function formatObservedAt(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return OBSERVED_AT_FORMATTER.format(date);
}

function createPersistIntentId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `persist-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getSuggestionSubmissionKey(result) {
  return JSON.stringify({
    field: result.field,
    value: result.value,
    model: result.model,
    observed_at: result.observed_at,
    response_id: result.foundry_response?.id ?? null,
  });
}

function buildSuggestionAuditPayload({ resourceId, result, persistIntentId }) {
  return {
    resource_id: resourceId,
    field: result.field,
    suggested_value: result.value,
    rationale: result.rationale,
    citations: result.citations,
    model: result.model,
    foundry_request: result.foundry_request,
    foundry_response: result.foundry_response,
    persist_intent_id: persistIntentId,
  };
}

function buildLLMSourcePayload({ resourceId, result, persistIntentId }) {
  const auditPayload = buildSuggestionAuditPayload({
    resourceId,
    result,
    persistIntentId,
  });

  // A bare source (no `id`) to be created and attached to the target resource.
  // `name`/`country` are required keys on the field model (null when unknown).
  return {
    source: "llm",
    name: null,
    country: null,
    [result.field]: result.value,
    source_record: {
      record_id: persistIntentId,
      run_id: null,
      observed_at: result.observed_at,
      producer: LLM_AUDIT_PRODUCER,
      payload: auditPayload,
    },
  };
}

function formatSuggestionValue(value) {
  if (value == null) return null;
  return String(value);
}

function SuggestionResult({ result }) {
  const fieldLabel = FIELD_META[result.field]?.label ?? result.field;
  const value = formatSuggestionValue(result.value);
  const hasCitations =
    Array.isArray(result.citations) && result.citations.length > 0;
  const isPlaceholder = result.model === "placeholder-llm";

  if (value == null) {
    return (
      <div className="rounded-md border border-line bg-panel p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-ink">{fieldLabel}</p>
            <p className="mt-1 text-sm text-ink-muted">
              No grounded suggestion was returned for this field.
            </p>
          </div>
          <span className="rounded-md border border-line bg-surface px-2 py-1 text-xs font-medium text-ink-muted">
            {isPlaceholder ? "Offline mode" : "No answer"}
          </span>
        </div>
        {result.rationale && (
          <p className="mt-3 text-sm leading-6 text-ink-muted">
            {result.rationale}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-md border border-line bg-panel p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-ink">{fieldLabel}</p>
          <p className="mt-1 text-2xl font-semibold text-ink">{value}</p>
        </div>
        <span className="rounded-md border border-primary/30 bg-primary-soft px-2 py-1 text-xs font-medium text-primary">
          {isPlaceholder ? "Offline mode" : "Suggested"}
        </span>
      </div>

      {result.rationale && (
        <p className="mt-3 text-sm leading-6 text-ink-muted">
          {result.rationale}
        </p>
      )}

      {hasCitations && (
        <div className="mt-4 border-t border-line pt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Sources
          </p>
          <ul className="mt-2 space-y-2 text-sm text-ink">
            {result.citations.map((citation) => (
              <li key={`${citation.url}-${citation.title ?? ""}`}>
                <a
                  href={citation.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary underline"
                >
                  {citation.title ?? citation.url}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function AISuggestionPanel({ endpoint, resourceId }) {
  const config = useConfig();
  const { getAccessTokenSilently } = useAuth0();
  const fetcher = createAuthenticatedFetcher(config, getAccessTokenSilently);
  const createSource = useCreateSourceForResource(endpoint);
  const [selectedField, setSelectedField] = useState(AI_SUGGESTION_FIELDS[0]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [persistState, setPersistState] = useState(null);

  const isPersisting = createSource.isPending;

  // Read the cached /auth/me permissions once. `isLoading` lets us hold a
  // placeholder instead of flashing the panel in once it loads.
  const { data: permissions, isLoading: permissionsLoading } = usePermissions();
  const hasPermission = (permission) =>
    Array.isArray(permissions) && permissions.includes(permission);
  // The whole panel is only useful to users who can run LLM suggestions.
  const canRunLlm = hasPermission("service:llm:suggest");
  // Creating + attaching a source needs both the source and resource writes.
  const canAttach =
    hasPermission("source:write") && hasPermission("resource:write");
  const canPersist = result?.value != null;
  const isPersistedCurrentSuggestion =
    result &&
    persistState?.status === "success" &&
    persistState.suggestionKey === getSuggestionSubmissionKey(result);

  async function handleGenerateSuggestion() {
    setIsLoading(true);
    setError("");
    setResult(null);
    setPersistState(null);

    try {
      const suggestion = await createLLMSuggestion(
        config,
        resourceId,
        selectedField,
        fetcher,
        endpoint,
      );
      setResult(suggestion);
    } catch (err) {
      setError(err.message || "Failed to generate suggestion.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handlePersistSuggestion() {
    if (!result || result.value == null) return;

    setError("");

    const persistIntentId = createPersistIntentId();
    const sourcePayload = buildLLMSourcePayload({
      resourceId,
      result,
      persistIntentId,
    });
    const suggestionKey = getSuggestionSubmissionKey(result);

    try {
      // Resolves after the mutation's cache invalidation, so the newly
      // attached source (and any change to the coalesced winning value)
      // shows immediately.
      const createdSource = await createSource.mutateAsync({
        resourceId,
        payload: sourcePayload,
      });
      setPersistState({
        status: "success",
        sourceId: createdSource.id,
        suggestionKey,
      });
    } catch (err) {
      setPersistState(null);
      setError(err.message || "Failed to add suggestion to resource.");
    }
  }

  // Hold a placeholder until permissions resolve, so the panel doesn't flash
  // in (or briefly appear then vanish) once /auth/me loads.
  if (permissionsLoading) {
    return (
      <section aria-hidden="true">
        <div
          data-testid="ai-suggestion-loading"
          className="h-28 animate-pulse rounded-md border border-line bg-surface"
        />
      </section>
    );
  }

  // Hide the entire panel from users who can't run LLM suggestions.
  if (!canRunLlm) return null;

  return (
    <section>
      <SectionHeader title="AI suggestion" />
      <div className="space-y-4 rounded-md border border-line bg-surface p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex-1 text-sm text-ink">
            <span className="mb-1 block font-medium">Field</span>
            <select
              value={selectedField}
              onChange={(event) => {
                setSelectedField(event.target.value);
                setError("");
                setResult(null);
              }}
              className="w-full rounded-md border border-line bg-panel px-3 py-2 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            >
              {AI_SUGGESTION_FIELDS.map((fieldKey) => (
                <option key={fieldKey} value={fieldKey}>
                  {FIELD_META[fieldKey].label}
                </option>
              ))}
            </select>
          </label>
          <Button
            onClick={handleGenerateSuggestion}
            disabled={isLoading}
            variant="secondary"
          >
            {isLoading ? "Generating…" : "Generate suggestion"}
          </Button>
        </div>

        {error && (
          <div className="rounded-md border border-danger/25 bg-danger-soft px-4 py-3 text-sm text-danger">
            {error}
          </div>
        )}

        {result && <SuggestionResult result={result} />}

        {canPersist && canAttach && (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <Button
              onClick={handlePersistSuggestion}
              disabled={isPersisting || isPersistedCurrentSuggestion}
              variant="secondary"
            >
              {isPersisting
                ? "Adding…"
                : isPersistedCurrentSuggestion
                  ? "Added to resource"
                  : "Add to resource"}
            </Button>

            {persistState?.status === "success" &&
              isPersistedCurrentSuggestion && (
                <p className="text-sm text-green-700">
                  Source added to resource.
                </p>
              )}
          </div>
        )}
      </div>
    </section>
  );
}

function OrgPanel({ items, nameLabel }) {
  if (items.length === 0) return <div className="flex-1" />;
  return (
    <div className="flex-1">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-5">
        {items.flatMap((o, idx) => [
          <FieldCard key={`name-${idx}`} label={nameLabel} value={o.name} />,
          <FieldCard
            key={`stake-${idx}`}
            label="Stake"
            value={o.stake == null ? null : `${o.stake}%`}
          />,
        ])}
      </div>
    </div>
  );
}

function OrganizationsSection({ data }) {
  const owners = data.owners ?? [];
  const operators = data.operators ?? [];

  if (owners.length === 0 && operators.length === 0) return null;

  return (
    <div className="flex flex-col md:flex-row">
      <OrgPanel items={owners} nameLabel={FIELD_META.owners.label} />
      {/* Horizontal divider on mobile, vertical on desktop */}
      <hr className="my-4 border-line md:hidden" />
      <div className="mx-6 hidden w-px self-stretch bg-line md:block" />
      <OrgPanel items={operators} nameLabel={FIELD_META.operators.label} />
    </div>
  );
}

function TechnicalImportRecord({ sourceRecord }) {
  const [isOpen, setIsOpen] = useState(false);
  const panelId = useId();

  return (
    <div className="rounded-md border border-line bg-surface">
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={panelId}
        onClick={() => setIsOpen((current) => !current)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold text-ink"
      >
        <span>Technical import record</span>
        <span aria-hidden="true" className="text-ink-muted">
          {isOpen ? "−" : "+"}
        </span>
      </button>
      {isOpen && (
        <div id={panelId} className="space-y-3 border-t border-line px-4 py-3">
          <FieldGrid>
            <FieldCard label="Record ID" value={sourceRecord.record_id} />
            <FieldCard label="Run ID" value={sourceRecord.run_id} />
          </FieldGrid>
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Raw payload
            </p>
            <pre className="overflow-x-auto rounded-md border border-line bg-panel p-4 text-xs leading-6 text-ink">
              {JSON.stringify(sourceRecord.payload, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

function SourceRow({ source }) {
  const [isOpen, setIsOpen] = useState(false);
  const panelId = useId();
  const hasId = Number.isFinite(source.id);
  const {
    data: sourceDetail,
    isLoading,
    isError,
    error,
  } = useSourceDetail("oil-gas-field-sources", source.id, hasId);

  const sourceLabel = SOURCE_LABELS[source.source] ?? source.source;
  const sourceRecord = sourceDetail?.source_record ?? null;
  // A curator's overwrite note, when this source was created via the field
  // overwrite action. Payload is arbitrary JSON, so guard the shape before use.
  const payload = sourceRecord?.payload;
  const overrideNote =
    payload &&
    typeof payload === "object" &&
    !Array.isArray(payload) &&
    typeof payload.note === "string" &&
    payload.note.trim()
      ? payload.note.trim()
      : null;

  let metaLine;
  if (sourceRecord) {
    const producer = sourceRecord.producer ?? "—";
    const observed = formatObservedAt(sourceRecord.observed_at);
    metaLine = (
      <span>
        Imported by {producer} · {observed}
      </span>
    );
  } else if (isLoading) {
    metaLine = <span className="text-ink-muted">Loading source details…</span>;
  } else if (isError) {
    metaLine = (
      <span className="text-danger">Unable to load source details</span>
    );
  } else {
    metaLine = <span className="text-ink-muted">Imported by — · —</span>;
  }

  return (
    <div className="rounded-md border border-line bg-panel p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            {sourceLabel}
          </p>
          <p className="text-sm text-ink">{metaLine}</p>
          <p className="text-xs text-ink-muted">
            {source.name ?? "Unnamed source"}
          </p>
        </div>
        <Button
          variant="secondary"
          aria-expanded={isOpen}
          aria-controls={panelId}
          disabled={!hasId}
          onClick={() => setIsOpen((current) => !current)}
        >
          {isOpen ? "Hide" : "View"}
        </Button>
      </div>

      {isOpen && (
        <div id={panelId} className="mt-4 space-y-4 border-t border-line pt-4">
          {isLoading && (
            <p className="text-sm text-ink-muted">Loading source details…</p>
          )}

          {isError && (
            <p className="text-sm text-danger">
              Failed to load source details
              {error?.message ? `: ${error.message}` : "."}
            </p>
          )}

          {sourceDetail && !sourceRecord && (
            <p className="text-sm text-ink-muted">
              No import record available.
            </p>
          )}

          {sourceRecord && (
            <>
              <FieldGrid>
                <FieldCard label="Source name" value={source.name} />
                <FieldCard label="Producer" value={sourceRecord.producer} />
                <FieldCard
                  label="Observed at"
                  value={formatObservedAt(sourceRecord.observed_at)}
                />
                <FieldCard label="Source row ID" value={source.id} />
              </FieldGrid>
              {overrideNote && (
                <div className="rounded-md border border-line bg-surface p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                    Note
                  </p>
                  <p className="mt-1 whitespace-pre-wrap break-words text-sm text-ink">
                    {overrideNote}
                  </p>
                </div>
              )}
              <TechnicalImportRecord sourceRecord={sourceRecord} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

function SourcesSection({ sources }) {
  const hasSources = Array.isArray(sources) && sources.length > 0;

  return (
    <section>
      <SectionHeader title="Sources" />
      {hasSources ? (
        <div className="space-y-4">
          {sources.map((source, idx) => (
            <SourceRow
              key={`${source.source}-${source.id ?? source.name ?? idx}`}
              source={source}
            />
          ))}
        </div>
      ) : (
        <p className="text-sm text-ink-muted">
          No sources attached to this resource.
        </p>
      )}
    </section>
  );
}

export default function ResourceDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const numericId = Number(id);
  const validId = Number.isFinite(numericId);
  const endpoint = "oil-gas-fields";
  // Enabled (not manually refetched) so that save mutations' cache
  // invalidations refetch it — invalidation never refetches disabled queries.
  const {
    data: detailView,
    isLoading,
    isError,
  } = useResourceDetail(endpoint, numericId, validId);

  useDocumentTitle(detailView?.data?.name ?? "Resource");

  return (
    <div className="mx-auto max-w-4xl">
      <Button onClick={() => navigate(-1)} variant="ghost" className="mb-6">
        ← Back
      </Button>

      {!validId && <p className="text-danger">Invalid resource ID.</p>}
      {isLoading && <p className="text-ink-muted">Loading…</p>}
      {isError && <p className="text-danger">Failed to load resource.</p>}

      {detailView && (
        <div className="space-y-10">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-ink">
              {detailView.data.name}
            </h1>
            {validId && (
              <p className="mt-1 font-mono text-xs text-ink-muted">
                {endpoint}/{numericId}
              </p>
            )}
          </div>

          <section>
            <SectionHeader title="Data source mix" />
            <div className="rounded-md border border-line bg-panel p-4">
              <SourceMixBar provenance={detailView.provenance} showLabels />
            </div>
          </section>

          {/* Identity & Location */}
          <section>
            <SectionHeader title="Identity and location" />
            <FieldGrid>
              {IDENTITY_FIELDS.map((key) => (
                <ResourceFieldCard
                  key={key}
                  endpoint={endpoint}
                  resourceId={numericId}
                  fieldKey={key}
                  label={FIELD_META[key].label}
                  value={detailView.data[key]}
                  source={detailView.provenance[key]}
                />
              ))}
            </FieldGrid>
          </section>

          {/* Organizations */}
          <section>
            <SectionHeader title="Organizations" />
            <OrganizationsSection data={detailView.data} />
          </section>

          {/* Production & Geology */}
          <section>
            <SectionHeader title="Production and geology" />
            <FieldGrid>
              {PRODUCTION_FIELDS.map((key) => (
                <ResourceFieldCard
                  key={key}
                  endpoint={endpoint}
                  resourceId={numericId}
                  fieldKey={key}
                  label={FIELD_META[key].label}
                  value={detailView.data[key]}
                  source={detailView.provenance[key]}
                />
              ))}
            </FieldGrid>
          </section>

          <AISuggestionPanel endpoint={endpoint} resourceId={numericId} />

          <SourcesSection sources={detailView.source_data} />
        </div>
      )}
    </div>
  );
}
