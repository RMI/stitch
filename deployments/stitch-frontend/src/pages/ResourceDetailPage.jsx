import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useResource } from "../hooks/useResources";
import SourceMixBar from "../components/SourceMixBar";
import SectionHeader from "../components/SectionHeader";
import { FieldCard, FieldGrid } from "../components/FieldCard";
import {
  FIELD_META,
  IDENTITY_FIELDS,
  PRODUCTION_FIELDS,
} from "../constants/fieldMeta";

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
  const { data, isLoading, isError, refetch } = useResource(numericId);

  useEffect(() => {
    refetch();
  }, [numericId]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="max-w-4xl mx-auto">
      <button
        onClick={() => navigate(-1)}
        className="mb-6 text-sm text-gray-dark  transition-colors border px-2 py-1.5 rounded-md bg-white hover:bg-gray-light border-gray-dark hover:cursor-pointer"
      >
        ← Back
      </button>

      {isLoading && <p className="text-gray-medium">Loading…</p>}
      {isError && <p className="text-red-500">Failed to load resource.</p>}

      {data && (
        <div className="space-y-12">
          {/* Header */}
          <div>
            <h1 className="text-3xl font-bold text-gray-dark mb-4">
              {data.name}
            </h1>
          </div>

          <section>
            <SectionHeader title="Data Source Mix" />
            <div className="px-4">
              <SourceMixBar sourceData={data.source_data} showLabels />
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
                  value={data[key]}
                />
              ))}
            </FieldGrid>
          </section>

          {/* Organizations */}
          <section>
            <SectionHeader title="Organizations" />
            <OrganizationsSection data={data} />
          </section>

          {/* Production & Geology */}
          <section>
            <SectionHeader title="Production and geology" />
            <FieldGrid>
              {PRODUCTION_FIELDS.map((key) => (
                <FieldCard
                  key={key}
                  label={FIELD_META[key].label}
                  value={data[key]}
                />
              ))}
            </FieldGrid>
          </section>

          <section className="bg-gray-light p-4">
            <pre>{JSON.stringify(data, null, 2)}</pre>
          </section>
        </div>
      )}
    </div>
  );
}
