import { useEffect, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useParams, useNavigate } from "react-router-dom";
import { useResourceDetail } from "../hooks/useResources";
import { createAuthenticatedFetcher } from "../auth/api";
import { useConfig } from "../config/useConfig";
import { createLLMSuggestion } from "../queries/api";
import SourceMixBar from "../components/SourceMixBar";
import SectionHeader from "../components/SectionHeader";
import { FieldCard, FieldGrid } from "../components/FieldCard";
import StructuredDataView from "../components/StructuredDataView";
import Button from "../components/Button";
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

function EvidenceDetails({ detailView }) {
  const evidence = {
    provenance: detailView.provenance,
    source_data: detailView.source_data,
  };

  return (
    <section>
      <SectionHeader title="Evidence details" />
      <details className="rounded-md border border-line bg-panel px-4 py-3">
        <summary className="cursor-pointer text-sm font-semibold text-ink">
          Source records and provenance
        </summary>
        <StructuredDataView
          data={evidence}
          label="Source records and provenance"
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

          <EvidenceDetails detailView={detailView} />
        </div>
      )}
    </div>
  );
}
