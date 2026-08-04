import { useState } from "react";
import { useSearchParams } from "react-router";
import { useResources } from "../hooks/useResources";
import ResourcesTable from "./ResourcesTable";
import FilterBar from "./FilterBar";
import Pagination from "./Pagination";
import Button from "./Button";
import Input from "./Input";
import { EMPTY_FILTERS } from "../config/filters";
import { DEFAULT_PAGE_SIZE, DEFAULT_PAGE } from "../queries/resources";
import { useConfig } from "../config/useConfig";

const COLUMN_LABELS = {
  name: "Name",
  country: "Country",
  state_province: "State/Province",
  region: "Region",
  basin: "Basin",
  field_status: "Field status",
  primary_hydrocarbon_group: "Primary hydrocarbon group",
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
  const [searchText, setSearchText] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
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
      q: submittedSearch || undefined,
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

  const handleSearchInputChange = (event) => {
    const newValue = event.target.value;
    setSearchText(newValue);
    if (newValue === "" && submittedSearch !== "") {
      setSubmittedSearch("");
      setSearchParams({
        page: String(DEFAULT_PAGE),
        page_size: String(pageSize),
      });
    }
  };

  const handleSearchSubmit = (event) => {
    event.preventDefault();
    const normalizedSearch = searchText.trim();
    setSearchText(normalizedSearch);
    setSubmittedSearch(normalizedSearch);
    setSearchParams({
      page: String(DEFAULT_PAGE),
      page_size: String(pageSize),
    });
  };

  const handleSearchClear = () => {
    setSearchText("");
    setSubmittedSearch("");
    setSearchParams({
      page: String(DEFAULT_PAGE),
      page_size: String(pageSize),
    });
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
        <form
          onSubmit={handleSearchSubmit}
          className="flex w-full flex-col gap-2 sm:flex-row sm:items-center"
        >
          <div className="relative min-w-0 flex-1">
            <Input
              type="search"
              value={searchText}
              onChange={handleSearchInputChange}
              placeholder="Search resources"
              aria-label="Search resources"
              className="w-full pr-10"
            />
            {searchText && (
              <button
                type="button"
                onClick={handleSearchClear}
                aria-label="Clear search"
                className="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-sm font-semibold text-ink-muted transition-colors hover:bg-rmiblue-100 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-energy/60"
              >
                <span aria-hidden="true">X</span>
              </button>
            )}
          </div>
          <Button type="submit" variant="secondary" className="sm:w-auto">
            Search
          </Button>
        </form>

        <div className="mt-3 border-t border-line pt-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Filters
          </p>
          {data && (
            <FilterBar
              endpoint={endpoint}
              filters={filters}
              onFiltersChange={handleFiltersChange}
            />
          )}
        </div>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm font-medium text-ink-muted">
        <span>{resources.length.toLocaleString()} shown</span>
        <span>Sort: {getSortLabel(sortConfig)}</span>
        <span>{activeFilterCount} active filters</span>
        {submittedSearch && <span>Search: {submittedSearch}</span>}
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
          No resources match the current search and filters.
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
          {submittedSearch && (
            <>
              <dt className="font-semibold text-ink">Search</dt>
              <dd>{submittedSearch}</dd>
            </>
          )}
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
