import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useResource } from "../hooks/useResources";
import FetchButton from "./FetchButton";
import ClearCacheButton from "./ClearCacheButton";
import JsonView from "./JsonView";
import Input from "./Input";
import { resourceKeys } from "../queries/resources";
import { useConfig } from "../config/useConfig";

export default function ResourceView({
  className = "",
  endpoint,
  initialID = null,
  showControls = true,
}) {
  const config = useConfig();
  const queryClient = useQueryClient();
  const [inputId, setInputId] = useState(1);
  const id = initialID ?? inputId;
  const { data, isLoading, isError, error, refetch } = useResource(
    endpoint,
    id,
  );

  useEffect(() => {
    if (!showControls && initialID != null) {
      refetch();
    }
  }, [showControls, initialID, refetch]);

  const handleClear = (id) => {
    queryClient.resetQueries({ queryKey: resourceKeys.view(endpoint, id) });
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      refetch();
    }
  };
  const headingClass = showControls
    ? "mb-3 text-2xl font-semibold text-ink"
    : "mb-3 text-lg font-semibold text-ink";
  const emptyMessage = showControls
    ? "No resource loaded. Click the button above to fetch a resource."
    : "Resource evidence has not loaded.";

  return (
    <div className={`mx-auto max-w-4xl ${className}`}>
      <h1 className={headingClass}>
        {showControls ? `Resource ID: ${id}` : `Resource #${id}`}
      </h1>
      {showControls && (
        <div className="pb-4 text-sm text-ink-muted">
          <span className="font-semibold">
            {config.apiBaseUrl}/{endpoint}
          </span>
        </div>
      )}

      {showControls && (
        <div className="mb-6 flex flex-wrap gap-2">
          <Input
            type="number"
            value={inputId}
            onChange={(e) => setInputId(Number(e.target.value))}
            onKeyDown={handleKeyDown}
            min={1}
            max={1000}
            className="w-24"
          />
          <FetchButton onFetch={() => refetch()} isLoading={isLoading} />
          <ClearCacheButton
            onClear={() => handleClear(id)}
            disabled={!data && !error}
          />
        </div>
      )}

      <JsonView
        data={data}
        isLoading={isLoading}
        isError={isError}
        error={error}
        message={emptyMessage}
      />
    </div>
  );
}
