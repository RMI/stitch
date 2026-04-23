import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useResources } from "../hooks/useResources";
import FetchButton from "./FetchButton";
import ClearCacheButton from "./ClearCacheButton";
import ResourcesTable from "./ResourcesTable";
import FilterBar from "./FilterBar";
import Pagination from "./Pagination";
import { EMPTY_FILTERS } from "../config/filters";
import {
  resourceKeys,
  DEFAULT_PAGE_SIZE,
  DEFAULT_PAGE,
} from "../queries/resources";
import { useConfig } from "../config/context";

export default function ResourcesView({ className, endpoint }) {
  const config = useConfig();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Number(searchParams.get("page") ?? DEFAULT_PAGE);
  const pageSize = Number(searchParams.get("page_size") ?? DEFAULT_PAGE_SIZE);
  const [enabled, setEnabled] = useState(false);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [sortConfig, setSortConfig] = useState({
    column: null,
    direction: "asc",
  });

  const { data, isLoading, isError, refetch } = useResources(endpoint, {
    page,
    page_size: pageSize,
    enabled,
    filters,
    sort_by: sortConfig.column ?? undefined,
    sort_order: sortConfig.column ? sortConfig.direction : undefined,
  });

  const handleFetch = () => {
    setEnabled(true);
    refetch();
  };

  const handleClear = () => {
    queryClient.removeQueries({ queryKey: resourceKeys.lists(endpoint) });
    setEnabled(false);
    setFilters(EMPTY_FILTERS);
    setSearchParams({});
  };

  const handlePageChange = (newPage) => {
    setSearchParams({ page: newPage, page_size: pageSize });
  };

  const handlePageSizeChange = (newSize) => {
    setSearchParams({ page: DEFAULT_PAGE, page_size: newSize });
  };

  const handleFiltersChange = (newFilters) => {
    setFilters(newFilters);
    setSearchParams({ page: DEFAULT_PAGE, page_size: pageSize });
  };

  const handleSortChange = (newSortConfig) => {
    setSortConfig(newSortConfig);
    setSearchParams({ page: DEFAULT_PAGE, page_size: pageSize });
  };

  return (
    <div className={`max-w-4xl mx-auto ${className}`}>
      <h1 className="text-3xl font-bold mb-3 text-gray-800">Resources</h1>
      <div className="text-gray-500 pb-4">
        <span className="font-bold">
          {config.apiBaseUrl}/{endpoint}
        </span>
      </div>
      <div className="mb-4 flex gap-3">
        <FetchButton onFetch={handleFetch} isLoading={isLoading} />
        <ClearCacheButton
          onClear={handleClear}
          disabled={!data?.items?.length && !isError}
        />
      </div>
      {data?.items?.length > 0 && (
        <div className="mb-4">
          <FilterBar
            resources={data?.items}
            filters={filters}
            onFiltersChange={handleFiltersChange}
          />
        </div>
      )}
      {isError && (
        <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          Failed to load resources. Check your connection and try again.
        </p>
      )}
      {!isError && data && data.items?.length === 0 && (
        <p className="text-sm text-gray-400">
          No resources match the current filters.
        </p>
      )}
      <ResourcesTable
        resources={data?.items}
        sortConfig={sortConfig}
        onSort={handleSortChange}
      />
      {data && (
        <Pagination
          page={page}
          pageSize={pageSize}
          totalCount={data.total_count}
          totalPages={data.total_pages}
          onPageChange={handlePageChange}
          onPageSizeChange={handlePageSizeChange}
        />
      )}
    </div>
  );
}
