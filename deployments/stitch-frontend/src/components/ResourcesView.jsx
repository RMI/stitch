import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useResources } from "../hooks/useResources";
import ResourcesTable from "./ResourcesTable";
import FilterBar from "./FilterBar";
import Pagination from "./Pagination";
import Button from "./Button";
import { EMPTY_FILTERS } from "../config/filters";
import { DEFAULT_PAGE_SIZE, DEFAULT_PAGE } from "../queries/resources";
import { useConfig } from "../config/useConfig";

const COLUMN_LABELS = {
  name: "Name",
  state_province: "State/Province",
  region: "Region",
  basin: "Basin",
  field_status: "Field status",
};

function getSortLabel(sortConfig) {
  if (!sortConfig.column) return "Name";

  const direction =
    sortConfig.direction === "desc" ? "descending" : "ascending";
  return `${COLUMN_LABELS[sortConfig.column] ?? sortConfig.column} ${direction}`;
}

export default function ResourcesView({ className = "", endpoint }) {
  const config = useConfig();
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Number(searchParams.get("page") ?? DEFAULT_PAGE);
  const pageSize = Number(searchParams.get("page_size") ?? DEFAULT_PAGE_SIZE);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [sortConfig, setSortConfig] = useState({
    column: null,
    direction: "asc",
  });

  const { data, isLoading, isFetching, isError, error, refetch } = useResources(
    endpoint,
    {
      page,
      page_size: pageSize,
      enabled: true,
      filters,
      sort_by: sortConfig.column ?? undefined,
      sort_order: sortConfig.column ? sortConfig.direction : undefined,
    },
  );

  const resources = data?.items ?? [];
  const totalCount = data?.total_count ?? 0;
  const totalPages = data?.total_pages ?? 0;
  const isRefreshing = isLoading || isFetching;
  const activeFilterCount = Object.values(filters).reduce(
    (count, values) => count + values.length,
    0,
  );

  const handleRefresh = () => {
    refetch();
  };

  const handlePageChange = (newPage) => {
    setSearchParams({ page: String(newPage), page_size: String(pageSize) });
  };

  const handlePageSizeChange = (newSize) => {
    setSearchParams({ page: String(DEFAULT_PAGE), page_size: String(newSize) });
  };

  const handleFiltersChange = (newFilters) => {
    setFilters(newFilters);
    setSearchParams({
      page: String(DEFAULT_PAGE),
      page_size: String(pageSize),
    });
  };

  const handleSortChange = (newSortConfig) => {
    setSortConfig(newSortConfig);
    setSearchParams({
      page: String(DEFAULT_PAGE),
      page_size: String(pageSize),
    });
  };

  return (
    <div className={`mx-auto w-full max-w-6xl ${className}`}>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-primary">
            Asset inventory
          </p>
          <h1 className="mt-1 text-3xl font-semibold text-ink">Resources</h1>
          <p className="mt-1 text-sm text-ink-muted">
            {data
              ? `${totalCount.toLocaleString()} assets`
              : "Awaiting resource count"}
          </p>
        </div>

        <Button
          onClick={handleRefresh}
          disabled={isRefreshing}
          variant="secondary"
        >
          {isRefreshing ? "Refreshing" : "Refresh"}
        </Button>
      </div>

      <div className="mb-4 rounded-md border border-line bg-panel p-3">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Filters
        </p>
        {resources.length > 0 && (
          <FilterBar
            resources={resources}
            filters={filters}
            onFiltersChange={handleFiltersChange}
          />
        )}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm font-medium text-ink-muted">
        <span>{resources.length.toLocaleString()} shown</span>
        <span>Sort: {getSortLabel(sortConfig)}</span>
        <span>{activeFilterCount} active filters</span>
      </div>

      {isLoading && resources.length === 0 && (
        <p className="rounded-md border border-line bg-surface px-4 py-3 text-sm text-ink-muted">
          Loading resources...
        </p>
      )}
      {isError && (
        <p className="rounded-md border border-danger/25 bg-danger-soft px-4 py-3 text-sm text-danger">
          Failed to load resources. Check your connection and try again.
        </p>
      )}
      {!isLoading && !isError && data && resources.length === 0 && (
        <p className="rounded-md border border-line bg-panel px-4 py-3 text-sm text-ink-muted">
          No resources match the current filters.
        </p>
      )}
      <ResourcesTable
        resources={resources}
        sortConfig={sortConfig}
        onSort={handleSortChange}
      />
      {data && totalCount > 0 && (
        <Pagination
          page={page}
          pageSize={pageSize}
          totalCount={data.total_count}
          totalPages={totalPages}
          onPageChange={handlePageChange}
          onPageSizeChange={handlePageSizeChange}
        />
      )}

      <details className="mt-5 border-t border-line pt-3 text-sm text-ink-muted">
        <summary className="cursor-pointer font-semibold text-ink-muted">
          Diagnostics
        </summary>
        <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-[8rem_1fr]">
          <dt className="font-semibold text-ink">Endpoint</dt>
          <dd className="break-all font-mono text-ink-muted">
            {config.apiBaseUrl}/{endpoint}
          </dd>
          <dt className="font-semibold text-ink">Page</dt>
          <dd>
            {page} of {totalPages || 0}, {pageSize} per page
          </dd>
          <dt className="font-semibold text-ink">Sort</dt>
          <dd>{getSortLabel(sortConfig)}</dd>
          {error && (
            <>
              <dt className="font-semibold text-ink">Last error</dt>
              <dd>{error.message}</dd>
            </>
          )}
        </dl>
      </details>
    </div>
  );
}
