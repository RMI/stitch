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
import {
  AI_SUGGESTION_FIELDS,
  FIELD_META,
  IDENTITY_FIELDS,
  PRODUCTION_FIELDS,
} from "../constants/fieldMeta";

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

        {error && <p className="text-sm text-red-500">{error}</p>}

        {result && (
          <div className="space-y-2 rounded-md bg-white p-4">
            <p className="text-sm text-gray-dark">
              <span className="font-medium">Field:</span>{" "}
              {FIELD_META[result.field]?.label ?? result.field}
            </p>
            <p className="text-sm text-gray-dark">
              <span className="font-medium">Suggested value:</span>{" "}
              {result.value == null ? "—" : String(result.value)}
            </p>
            {Array.isArray(result.citations) && result.citations.length > 0 && (
              <div className="space-y-1">
                <p className="text-sm font-medium text-gray-dark">Citations</p>
                <ul className="space-y-1 text-sm text-gray-dark">
                  {result.citations.map((citation) => (
                    <li key={`${citation.url}-${citation.title ?? ""}`}>
                      <a
                        href={citation.url}
                        target="_blank"
                        rel="noreferrer"
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
      <hr className="md:hidden my-4 border-gray-dark" />
      <div className="hidden md:block w-px bg-gray-dark mx-6 self-stretch" />
      <OrgPanel items={operators} nameLabel={FIELD_META.operators.label} />
    </div>
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

          <section className="bg-gray-light p-4">
            <pre>{JSON.stringify(detailView, null, 2)}</pre>
          </section>
        </div>
      )}
    </div>
  );
}
