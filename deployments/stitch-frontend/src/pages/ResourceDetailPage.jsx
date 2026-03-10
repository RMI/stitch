import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useResource } from "../hooks/useResources";

export default function ResourceDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const numericId = Number(id);
  const validId = Number.isFinite(numericId);
  const { data, isLoading, isError, refetch } = useResource(numericId);

  useEffect(() => {
    if (validId) refetch();
  }, [numericId, validId, refetch]);

  return (
    <div className="max-w-4xl mx-auto">
      <button
        onClick={() => navigate(-1)}
        className="mb-6 text-sm text-gray-500 hover:text-gray-800 transition-colors"
      >
        ← Back
      </button>

      {!validId && <p className="text-red-500">Invalid resource ID.</p>}
      {isLoading && <p className="text-gray-500">Loading…</p>}
      {isError && <p className="text-red-500">Failed to load resource.</p>}
      {data && (
        <div>
          <p className="text-sm text-gray-400 mb-1">ID: {data.id}</p>
          <h1 className="text-3xl font-bold text-gray-800">{data.name}</h1>
          <p className="text-base text-gray-500">{data.basin}</p>
        </div>
      )}
    </div>
  );
}
