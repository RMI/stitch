import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useResources } from "../hooks/useResources";
import FetchButton from "./FetchButton";
import ClearCacheButton from "./ClearCacheButton";
import ResourcesTable from "./ResourcesTable";
import FilterBar from "./FilterBar";
import { EMPTY_FILTERS } from "../config/filters";
import { resourceKeys } from "../queries/resources";

// OR within a field, AND across fields.
function applyFilters(resources, filters) {
  if (!resources) return resources;
  return resources.filter((resource) =>
    Object.entries(filters).every(
      ([field, values]) => !values.length || values.includes(resource[field]),
    ),
  );
}

export default function ResourcesView({ className, endpoint }) {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, refetch } = useResources();
  const [filters, setFilters] = useState(EMPTY_FILTERS);

  const handleClear = () => {
    queryClient.setQueryData(resourceKeys.lists(), []);
  };

  const filteredData = applyFilters(data, filters);

  return (
    <div className={`max-w-4xl mx-auto ${className}`}>
      <h1 className="text-3xl font-bold mb-3 text-gray-800">Resources</h1>
      <div className="text-gray-500 pb-4">
        <span className="font-bold">{endpoint}</span>
      </div>
      <div className="mb-4 flex gap-3">
        <FetchButton onFetch={() => refetch()} isLoading={isLoading} />
        <ClearCacheButton
          onClear={handleClear}
          disabled={!data?.length && !isError}
        />
      </div>
      {data?.length > 0 && (
        <div className="mb-4">
          <FilterBar
            resources={data}
            filters={filters}
            onFiltersChange={setFilters}
          />
        </div>
      )}
      {isError && (
        <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          Failed to load resources. Check your connection and try again.
        </p>
      )}
      {!isError && data && filteredData?.length === 0 && (
        <p className="text-sm text-gray-400">No resources match the current filters.</p>
      )}
      <ResourcesTable resources={filteredData} />
    </div>
  );
}
