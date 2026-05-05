import { useDeferredValue, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useResources } from "../hooks/useResources";
import ClearCacheButton from "./ClearCacheButton";
import ResourcesTable from "./ResourcesTable";
import FilterBar from "./FilterBar";
import Pagination from "./Pagination";
import Input from "./Input";
import { EMPTY_FILTERS } from "../config/filters";
import {
  resourceKeys,
  DEFAULT_PAGE_SIZE,
  DEFAULT_PAGE,
} from "../queries/resources";
import { useConfig } from "../config/useConfig";

export default function ResourcesView({ className, endpoint }) {
  const config = useConfig();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Number(searchParams.get("page") ?? DEFAULT_PAGE);
  const pageSize = Number(searchParams.get("page_size") ?? DEFAULT_PAGE_SIZE);
  const [searchText, setSearchText] = useState("");
  const deferredSearchText = useDeferredValue(searchText.trim());
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [sortConfig, setSortConfig] = useState({
    column: null,
    direction: "asc",
  });

  const { data, isLoading, isError } = useResources(endpoint, {
    page,
    page_size: pageSize,
    filters,
    q: deferredSearchText || undefined,
    sort_by: sortConfig.column ?? undefined,
    sort_order: sortConfig.column ? sortConfig.direction : undefined,
  });

  const handleClear = () => {
    queryClient.resetQueries({ queryKey: resourceKeys.lists(endpoint) });
    setSearchText("");
    setFilters(EMPTY_FILTERS);
    setSortConfig({
      column: null,
      direction: "asc",
    });
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

  const handleSearchChange = (event) => {
    setSearchText(event.target.value);
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
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <Input
          type="search"
          value={searchText}
          onChange={handleSearchChange}
          placeholder="Search fields"
          aria-label="Search resources"
          className="w-full sm:max-w-md"
        />
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
      {isLoading && (
        <p className="rounded-md border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-700">
          Loading resources...
        </p>
      )}
      {!isError && data && data.items?.length === 0 && (
        <p className="text-sm text-gray-400">
          No resources match the current search and filters.
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
