import { useEffect, useId, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useParams, useNavigate } from "react-router-dom";
import { useResourceDetail, useSourceDetail } from "../hooks/useResources";
import { createAuthenticatedFetcher } from "../auth/api";
import { useConfig } from "../config/useConfig";
import { createLLMSuggestion } from "../queries/api";
import SourceMixBar from "../components/SourceMixBar";
import SectionHeader from "../components/SectionHeader";
import { FieldCard, FieldGrid } from "../components/FieldCard";
import { SOURCE_LABELS } from "../constants/sourceMeta";
import {
  AI_SUGGESTION_FIELDS,
  FIELD_META,
  IDENTITY_FIELDS,
  PRODUCTION_FIELDS,
} from "../constants/fieldMeta";

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
      <div className="rounded-md border border-gray-dark/10 bg-white p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-gray-dark">{fieldLabel}</p>
            <p className="mt-1 text-sm text-gray-dark/80">
              No grounded suggestion was returned for this field.
            </p>
          </div>
          <span className="rounded border border-gray-dark/15 bg-gray-light px-2 py-1 text-xs text-gray-dark/70">
            {isPlaceholder ? "Offline mode" : "No answer"}
          </span>
        </div>
        {result.rationale && (
          <p className="mt-3 text-sm leading-6 text-gray-dark/80">
            {result.rationale}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-md border border-gray-dark/10 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-gray-dark">{fieldLabel}</p>
          <p className="mt-1 text-2xl font-semibold text-gray-dark">{value}</p>
        </div>
        <span className="rounded border border-gray-dark/15 bg-gray-light px-2 py-1 text-xs text-gray-dark/70">
          {isPlaceholder ? "Offline mode" : "Suggested"}
        </span>
      </div>

      {result.rationale && (
        <p className="mt-3 text-sm leading-6 text-gray-dark/80">
          {result.rationale}
        </p>
      )}

      {hasCitations && (
        <div className="mt-4 border-t border-gray-dark/10 pt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-dark/60">
            Sources
          </p>
          <ul className="mt-2 space-y-2 text-sm text-gray-dark">
            {result.citations.map((citation) => (
              <li key={`${citation.url}-${citation.title ?? ""}`}>
                <a
                  href={citation.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-700 underline"
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

  async function handleGenerateSuggestion() {
    setIsLoading(true);
    setError("");
    setResult(null);

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

  return (
    <section>
      <SectionHeader title="AI Suggestion" />
      <div className="rounded-md border border-gray-dark/20 bg-gray-light p-4 space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex-1 text-sm text-gray-dark">
            <span className="mb-1 block font-medium">Field</span>
            <select
              value={selectedField}
              onChange={(event) => {
                setSelectedField(event.target.value);
                setError("");
                setResult(null);
              }}
              className="w-full rounded-md border border-gray-dark bg-white px-3 py-2"
            >
              {AI_SUGGESTION_FIELDS.map((fieldKey) => (
                <option key={fieldKey} value={fieldKey}>
                  {FIELD_META[fieldKey].label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={handleGenerateSuggestion}
            disabled={isLoading}
            className="rounded-md border border-gray-dark bg-white px-4 py-2 text-sm hover:cursor-pointer disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isLoading ? "Generating…" : "Generate suggestion"}
          </button>
        </div>

        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {result && <SuggestionResult result={result} />}
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
      <hr className="md:hidden my-4 border-gray-dark" />
      <div className="hidden md:block w-px bg-gray-dark mx-6 self-stretch" />
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
    <div className="max-w-4xl mx-auto">
      <button
        onClick={() => navigate(-1)}
        className="mb-6 text-sm text-gray-dark  transition-colors border px-2 py-1.5 rounded-md bg-white hover:bg-gray-light border-gray-dark hover:cursor-pointer"
      >
        ← Back
      </button>

      {!validId && <p className="text-red-500">Invalid resource ID.</p>}
      {isLoading && <p className="text-gray-500">Loading…</p>}
      {isError && <p className="text-red-500">Failed to load resource.</p>}

      {detailView && (
        <div className="space-y-12">
          {/* Header */}
          <div>
            <h1 className="text-3xl font-bold text-gray-dark mb-4">
              {detailView.data.name}
            </h1>
          </div>

          <section>
            <SectionHeader title="Data Source Mix" />
            <div className="px-4">
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

          <section className="bg-gray-light p-4">
            <pre>{JSON.stringify(detailView, null, 2)}</pre>
          </section>
        </div>
      )}
    </div>
  );
}
