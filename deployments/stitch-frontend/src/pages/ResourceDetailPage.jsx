import { useEffect, useId, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useParams, useNavigate } from "react-router-dom";
import { useResourceDetail, useSourceDetail } from "../hooks/useResources";
import { createAuthenticatedFetcher } from "../auth/api";
import { useConfig } from "../config/useConfig";
import {
  createLLMSuggestion,
  createMergeCandidate,
  createResource,
} from "../queries/api";
import SourceMixBar from "../components/SourceMixBar";
import SectionHeader from "../components/SectionHeader";
import { FieldCard, FieldGrid } from "../components/FieldCard";
import { SOURCE_LABELS } from "../constants/sourceMeta";
import StructuredDataView from "../components/StructuredDataView";
import Button from "../components/Button";
import {
  AI_SUGGESTION_FIELDS,
  FIELD_META,
  IDENTITY_FIELDS,
  PRODUCTION_FIELDS,
} from "../constants/fieldMeta";

const LLM_AUDIT_PRODUCER = "stitch-frontend";
const UNSAFE_OBJECT_KEYS = new Set(["__proto__", "constructor", "prototype"]);

function canonicalizeJson(value) {
  if (Array.isArray(value)) {
    return value.map(canonicalizeJson);
  }
  if (value && typeof value === "object") {
    return Object.keys(value)
      .sort()
      .reduce((acc, key) => {
        if (UNSAFE_OBJECT_KEYS.has(key)) return acc;
        acc[key] = canonicalizeJson(value[key]);
        return acc;
      }, Object.create(null));
  }
  return value;
}

function stableJsonStringify(value) {
  return JSON.stringify(canonicalizeJson(value));
}

function createPersistIntentId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `persist-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getSuggestionSubmissionKey(result) {
  return stableJsonStringify({
    field: result.field,
    value: result.value,
    model: result.model,
    observed_at: result.observed_at,
    foundry_response: result.foundry_response,
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

function buildLLMResourcePayload({ resourceId, result, persistIntentId }) {
  const auditPayload = buildSuggestionAuditPayload({
    resourceId,
    result,
    persistIntentId,
  });

  return {
    id: null,
    repointed_to: null,
    constituents: [],
    provenance: {},
    view: null,
    source_data: [
      {
        id: null,
        source: "llm",
        name: null,
        country: null,
        [result.field]: result.value,
        source_record: {
          kind: "llm_audit",
          record_id: persistIntentId,
          run_id: null,
          observed_at: result.observed_at,
          producer: LLM_AUDIT_PRODUCER,
          payload: auditPayload,
        },
      },
    ],
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
  const [selectedField, setSelectedField] = useState(AI_SUGGESTION_FIELDS[0]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isPersisting, setIsPersisting] = useState(false);
  const [persistState, setPersistState] = useState(null);

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

    setIsPersisting(true);
    setError("");

    const persistIntentId = createPersistIntentId();
    const resourcePayload = buildLLMResourcePayload({
      resourceId,
      result,
      persistIntentId,
    });
    const suggestionKey = getSuggestionSubmissionKey(result);

    try {
      const createdResource = await createResource(
        config,
        resourcePayload,
        fetcher,
        endpoint,
      );

      try {
        const mergeCandidate = await createMergeCandidate(
          config,
          [resourceId, createdResource.id],
          fetcher,
          endpoint,
        );
        setPersistState({
          status: "success",
          resourceId: createdResource.id,
          candidateId: mergeCandidate.id,
          suggestionKey,
        });
      } catch {
        setPersistState({
          status: "partial",
          resourceId: createdResource.id,
          suggestionKey,
        });
        setError(
          `Suggestion saved as resource ${createdResource.id}, but the merge draft was not created.`,
        );
      }
    } catch (err) {
      setPersistState(null);
      setError(err.message || "Failed to persist suggestion.");
    } finally {
      setIsPersisting(false);
    }
  }

  return (
    <section>
      <SectionHeader title="AI Suggestion" />
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

        {canPersist && (
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
                  Suggestion saved and queued for later merge review.
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
            value={`${o.stake}%`}
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

function SourceDetailCard({ source }) {
  const [isOpen, setIsOpen] = useState(false);
  const panelId = useId();
  const hasId = Number.isFinite(source.id);
  const {
    data: sourceDetail,
    isLoading,
    isError,
    error,
  } = useSourceDetail("oil-gas-field-sources", source.id, isOpen && hasId);
  const sourceLabel = SOURCE_LABELS[source.source] ?? source.source;

  return (
    <div className="rounded-md border border-gray-dark/15 bg-white p-4 space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-dark/60">
            {sourceLabel}
          </p>
          <p className="text-lg font-semibold text-gray-dark">
            {source.name ?? "Unnamed source"}
          </p>
          <p className="text-sm text-gray-dark/70">
            Source row ID: {source.id ?? "Unavailable"}
          </p>
        </div>
        <button
          type="button"
          disabled={!hasId}
          aria-expanded={isOpen}
          aria-controls={panelId}
          onClick={() => setIsOpen((current) => !current)}
          className="rounded-md border border-gray-dark bg-gray-light px-3 py-2 text-sm text-gray-dark hover:cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isOpen ? "Hide details" : "Show details"}
        </button>
      </div>

      {isOpen && (
        <div
          id={panelId}
          className="space-y-3 border-t border-gray-dark/10 pt-4"
        >
          {isLoading && (
            <p className="text-sm text-gray-dark/70">Loading source details…</p>
          )}

          {isError && (
            <p className="text-sm text-red-600">
              Failed to load source details
              {error?.message ? `: ${error.message}` : "."}
            </p>
          )}

          {sourceDetail && (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <FieldCard
                  label="Source Hash"
                  value={sourceDetail.source_record_hash}
                />
                <FieldCard
                  label="Producer"
                  value={sourceDetail.source_record?.producer}
                />
              </div>
              <div className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-dark/60">
                  Source Record
                </p>
                <pre className="overflow-x-auto rounded-md bg-gray-light p-4 text-xs leading-6 text-gray-dark">
                  {JSON.stringify(sourceDetail.source_record, null, 2)}
                </pre>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function SourceDetailsSection({ sources }) {
  if (!Array.isArray(sources) || sources.length === 0) return null;

  return (
    <section>
      <SectionHeader title="Source Details" />
      <div className="space-y-4">
        {sources.map((source) => (
          <SourceDetailCard
            key={`${source.source}-${source.id ?? source.name ?? "source"}`}
            source={source}
          />
        ))}
      </div>
    </section>
  );
}

function SourceDataSection({ sourceData }) {
  return (
    <section>
      <SectionHeader title="Source data" />
      <details className="rounded-md border border-line bg-panel px-4 py-3">
        <summary className="cursor-pointer text-sm font-semibold text-ink">
          Source records
        </summary>
        <StructuredDataView
          data={sourceData}
          label="Source records"
          className="mt-4"
        />
      </details>
    </section>
  );
}

export default function ResourceDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const numericId = Number(id);
  const validId = Number.isFinite(numericId);
  const endpoint = "oil-gas-fields";
  const {
    data: detailView,
    isLoading,
    isError,
    refetch,
  } = useResourceDetail(endpoint, numericId);

  useEffect(() => {
    if (validId) refetch();
  }, [numericId, validId, refetch]);

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
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">
              Curated resource
            </p>
            <h1 className="mt-1 text-3xl font-semibold text-ink">
              {detailView.data.name}
            </h1>
          </div>

          <section>
            <SectionHeader title="Data Source Mix" />
            <div className="rounded-md border border-line bg-panel p-4">
              <SourceMixBar provenance={detailView.provenance} showLabels />
            </div>
          </section>

          {/* Identity & Location */}
          <section>
            <SectionHeader title="Identity and location" />
            <FieldGrid>
              {IDENTITY_FIELDS.map((key) => (
                <FieldCard
                  key={key}
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
                <FieldCard
                  key={key}
                  label={FIELD_META[key].label}
                  value={detailView.data[key]}
                  source={detailView.provenance[key]}
                />
              ))}
            </FieldGrid>
          </section>

          <AISuggestionPanel endpoint={endpoint} resourceId={numericId} />

          <SourceDetailsSection sources={detailView.source_data} />

          <SourceDataSection sourceData={detailView.source_data} />
        </div>
      )}
    </div>
  );
}
