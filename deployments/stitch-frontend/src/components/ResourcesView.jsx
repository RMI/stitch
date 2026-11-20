import { useState } from "react";
import { Link } from "react-router";
import { useResources, useCreateMergeCandidate } from "../hooks/useResources";
import { useHasPermission } from "../hooks/usePermissions";
import { useListState } from "../hooks/useListState";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import ResourcesTable from "./ResourcesTable";
import FilterBar from "./FilterBar";
import Pagination from "./Pagination";
import Button from "./Button";
import Input from "./Input";
import { useConfig } from "../config/useConfig";
import {
  getRememberedMergeSelection,
  rememberMergeSelection,
} from "../config/mergeSelection";
import { getResourceField } from "../utils/resourceDisplay";
import { getCountryName } from "../constants/countries";

const COLUMN_LABELS = {
  name: "Name",
  country: "Country",
  state_province: "State/Province",
  region: "Region",
  basin: "Basin",
  field_status: "Field status",
  primary_hydrocarbon_group: "Primary hydrocarbon group",
};

// A merge candidate joins exactly two resources, so the selection caps at
// two. The backend accepts >=2, but surfacing larger groups here would
// promise more than the review page is designed to handle.
const MERGE_SELECTION_LIMIT = 2;

const MERGE_REVIEW_PATH = "/merge-candidate-review";

// The API answers a rejected proposal with a developer-facing sentence (e.g.
// "A pending merge candidate already exists for resources [3, 7]."), so the
// cases a user can hit by picking a pair are reworded here. Matching on the
// message is the only signal the API gives; anything unrecognised falls back
// to the API's own text.
function getProposeMergeErrorMessage(error) {
  const message = error?.message ?? "";
  if (/pending merge candidate already exists/i.test(message)) {
    return "These two fields are already waiting for review.";
  }
  if (/approved merge candidate already exists/i.test(message)) {
    return "These two fields have already been merged.";
  }
  if (/denied merge candidate already exists/i.test(message)) {
    return "A reviewer has already decided these two fields are not the same.";
  }
  if (/already been merged/i.test(message)) {
    return "One of these fields has already been merged into another. Remove it and pick again.";
  }
  if (error?.status === 404) {
    return "One of these fields no longer exists. Remove it and pick again.";
  }
  return `Could not propose the merge: ${message || "unknown error"}`;
}

// Floats at the bottom of the screen while a merge is being picked, naming the
// picked fields so they stay visible when they are on another page or
// filtered out. After a successful proposal it confirms and links to review.
function MergeSelectionBar({
  selection,
  onRemove,
  onClear,
  onPropose,
  onDismissProposed,
  isProposing,
  proposeError,
  wasProposed,
}) {
  if (!selection.length && !wasProposed) return null;

  const barClassName =
    "sticky bottom-4 z-10 mt-4 rounded-md border border-line-strong/40 bg-panel p-3 text-sm shadow-lg";

  if (!selection.length) {
    return (
      <div
        role="status"
        className={`${barClassName} flex flex-wrap items-center gap-3`}
      >
        <span className="font-semibold text-ink">Merge proposed.</span>
        <Link
          to={MERGE_REVIEW_PATH}
          className="font-semibold text-primary underline underline-offset-4"
        >
          Review now →
        </Link>
        <Button
          variant="ghost"
          onClick={onDismissProposed}
          className="ml-auto"
          aria-label="Dismiss"
        >
          <span aria-hidden="true">×</span>
        </Button>
      </div>
    );
  }

  const isComplete = selection.length === MERGE_SELECTION_LIMIT;

  return (
    <section aria-label="Merge selection" className={barClassName}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-ink">Merge</span>
        <ul className="flex flex-wrap items-center gap-2">
          {selection.map((entry) => {
            const name = entry.name ?? `Unnamed field ${entry.id}`;
            return (
              <li
                key={entry.id}
                className="flex items-center gap-1 rounded-full border border-line bg-primary-soft/40 py-0.5 pl-3 pr-1"
              >
                <span className="text-ink">{name}</span>
                {entry.country && (
                  <span className="text-ink-muted">· {entry.country}</span>
                )}
                <button
                  type="button"
                  onClick={() => onRemove(entry.id)}
                  aria-label={`Remove ${name} from merge`}
                  className="flex h-6 w-6 items-center justify-center rounded-full text-ink-muted hover:bg-rmiblue-100 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-energy/60"
                >
                  <span aria-hidden="true">×</span>
                </button>
              </li>
            );
          })}
          {!isComplete && (
            <li className="rounded-full border border-dashed border-line-strong/60 px-3 py-0.5 text-ink-muted">
              Pick one more field
            </li>
          )}
        </ul>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="ghost" onClick={onClear}>
            Clear
          </Button>
          <Button onClick={onPropose} disabled={!isComplete || isProposing}>
            {isProposing ? "Proposing..." : "Propose merge"}
          </Button>
        </div>
      </div>
      {proposeError && (
        <p role="alert" className="mt-2 text-danger">
          {getProposeMergeErrorMessage(proposeError)}
        </p>
      )}
    </section>
  );
}

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

  // The controls reflect every click immediately, but the query waits until
  // clicking settles so a burst of filter/sort/page changes sends one request.
  // The params are serialized because `filters` is a new object each render,
  // which would otherwise restart the debounce timer forever.
  const listParamsKey = JSON.stringify({
    page,
    page_size: pageSize,
    filters,
    q: q || undefined,
    sort_by: sort.column ?? undefined,
    sort_order: sort.column ? sort.direction : undefined,
  });
  const debouncedListParamsKey = useDebouncedValue(listParamsKey);

  // Rebuilt field by field: JSON drops undefined keys, and useResources should
  // see the same param shape whether or not a search or sort is active.
  const settledListParams = JSON.parse(debouncedListParamsKey);

  const { data, isLoading, isFetching, isError, error, refetch } = useResources(
    endpoint,
    {
      page: settledListParams.page,
      page_size: settledListParams.page_size,
      enabled: true,
      filters: settledListParams.filters,
      q: settledListParams.q,
      sort_by: settledListParams.sort_by,
      sort_order: settledListParams.sort_order,
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

  // Row-level multi-select feeds the merge bar below. Only rendered when the
  // caller can create merge candidates; the backend enforces the same
  // permission. The selection is remembered for the session so it survives
  // opening a resource to check it and coming back.
  const canProposeMerge = useHasPermission("merge-candidate:create");
  const [mergeSelection, setMergeSelection] = useState(() =>
    getRememberedMergeSelection(endpoint),
  );
  const selectedIds = new Set(mergeSelection.map((entry) => entry.id));
  const createMergeCandidate = useCreateMergeCandidate(endpoint);

  const saveMergeSelection = (next) => {
    setMergeSelection(next);
    rememberMergeSelection(endpoint, next);
  };

  // Any change to the picked pair makes the last proposal's outcome (an error
  // or the "proposed" confirmation) stale, so it is cleared alongside.
  const changeMergeSelection = (next) => {
    createMergeCandidate.reset();
    saveMergeSelection(next);
  };

  const handleToggleSelect = (resource) => {
    if (selectedIds.has(resource.id)) {
      changeMergeSelection(
        mergeSelection.filter((entry) => entry.id !== resource.id),
      );
    } else if (mergeSelection.length < MERGE_SELECTION_LIMIT) {
      const country = getResourceField(resource, "country");
      changeMergeSelection([
        ...mergeSelection,
        {
          id: resource.id,
          name: getResourceField(resource, "name"),
          country: country != null ? getCountryName(country) : null,
        },
      ]);
    }
  };

  const handleRemoveFromMerge = (id) =>
    changeMergeSelection(mergeSelection.filter((entry) => entry.id !== id));

  const handleClearMergeSelection = () => changeMergeSelection([]);

  // Stays on the list so the user can keep working through it; the bar then
  // confirms the proposal and links to the review queue.
  const handleProposeMerge = () => {
    createMergeCandidate.mutate(
      mergeSelection.map((entry) => entry.id),
      { onSuccess: () => saveMergeSelection([]) },
    );
  };

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
            optionParams={{
              filters: settledListParams.filters,
              q: settledListParams.q,
            }}
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
        selectedIds={selectedIds}
        onToggleSelect={canProposeMerge ? handleToggleSelect : undefined}
        selectionAtLimit={selectedIds.size >= MERGE_SELECTION_LIMIT}
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
      {canProposeMerge && (
        <MergeSelectionBar
          selection={mergeSelection}
          onRemove={handleRemoveFromMerge}
          onClear={handleClearMergeSelection}
          onPropose={handleProposeMerge}
          onDismissProposed={() => createMergeCandidate.reset()}
          isProposing={createMergeCandidate.isPending}
          proposeError={createMergeCandidate.error}
          wasProposed={createMergeCandidate.isSuccess}
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
