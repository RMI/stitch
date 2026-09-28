import { useState } from "react";
import { useResources } from "../hooks/useResources";
import { useListState } from "../hooks/useListState";
import ResourcesTable from "./ResourcesTable";
import FilterBar from "./FilterBar";
import Pagination from "./Pagination";
import Button from "./Button";
import Input from "./Input";
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
  const {
    page,
    pageSize,
    q,
    filters,
    sort,
    setPage,
    setPageSize,
    setSearch,
    setSort,
    setFilters,
  } = useListState();

  // The search box holds its own text while you type; only submit and clear
  // write to the URL, so typing does not rewrite history or refetch per
  // keystroke. When the URL's q changes underneath us — back/forward, or the
  // logotype reset — re-seed the box to match. This is React's documented
  // "adjusting state when a prop changes" pattern, which avoids an effect.
  const [searchText, setSearchText] = useState(q);
  const [lastQ, setLastQ] = useState(q);
  if (q !== lastQ) {
    setLastQ(q);
    setSearchText(q);
  }

  const { data, isLoading, isFetching, isError, error, refetch } = useResources(
    endpoint,
    {
      page,
      page_size: pageSize,
      enabled: true,
      filters,
      q: q || undefined,
      sort_by: sort.column ?? undefined,
      sort_order: sort.column ? sort.direction : undefined,
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

  const handlePageChange = (newPage) => setPage(newPage);

  const handlePageSizeChange = (newSize) => setPageSize(newSize);

  const handleSearchInputChange = (event) => {
    const newValue = event.target.value;
    setSearchText(newValue);
    if (newValue === "" && q !== "") {
      setSearch("");
    }
  };

  const handleSearchSubmit = (event) => {
    event.preventDefault();
    const normalizedSearch = searchText.trim();
    setSearchText(normalizedSearch);
    setSearch(normalizedSearch);
  };

  const handleSearchClear = () => {
    setSearchText("");
    setSearch("");
  };

  const handleFiltersChange = (newFilters) => setFilters(newFilters);

  const handleSortChange = (newSortConfig) => setSort(newSortConfig);

  return (
    <div className={`mx-auto w-full max-w-6xl ${className}`}>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            Resources
          </h1>
          <p className="mt-1 text-sm text-ink-muted">
            {data ? (
              <>
                <span className="font-mono tabular-nums text-ink">
                  {totalCount.toLocaleString()}
                </span>{" "}
                assets
              </>
            ) : (
              "Awaiting resource count"
            )}
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
                className="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-base leading-none text-ink-muted transition-colors hover:bg-rmiblue-100 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-energy/60"
              >
                <span aria-hidden="true">×</span>
              </button>
            )}
          </div>
          <Button type="submit" variant="secondary" className="sm:w-auto">
            Search
          </Button>
        </form>

        <div className="mt-3 border-t border-line pt-3">
          <FilterBar
            endpoint={endpoint}
            filters={filters}
            onFiltersChange={handleFiltersChange}
          />
        </div>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-muted">
        <span>
          <span className="font-mono tabular-nums text-ink">
            {resources.length.toLocaleString()}
          </span>{" "}
          shown
        </span>
        <span>Sort: {getSortLabel(sort)}</span>
        <span>
          <span className="font-mono tabular-nums text-ink">
            {activeFilterCount}
          </span>{" "}
          active filters
        </span>
        {q && (
          <span>
            Search: <span className="font-mono text-ink">{q}</span>
          </span>
        )}
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
        sortConfig={sort}
        onSort={handleSortChange}
        isFetching={isFetching}
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
          <dd>{getSortLabel(sort)}</dd>
          {q && (
            <>
              <dt className="font-semibold text-ink">Search</dt>
              <dd>{q}</dd>
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
