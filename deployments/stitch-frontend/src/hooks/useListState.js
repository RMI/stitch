/**
 * Reads and writes the resources list view state from the URL.
 *
 * The URL is the single source of truth — there is no local copy and no effect
 * syncing the two, which is where this kind of state usually rots. Every setter
 * round-trips the complete state through the schema, so writing one part can
 * never silently drop another.
 *
 * History: refining the view (filters, sort, search) rewrites the current entry
 * so a session of toggling filters does not bury the page you arrived from.
 * Paging pushes, so Back steps through pages.
 */
import { useSearchParams } from "react-router";
import { parseListParams, toListParams } from "../config/listParams";
import { DEFAULT_PAGE } from "../queries/resources";

export function useListState() {
  const [searchParams, setSearchParams] = useSearchParams();
  const state = parseListParams(searchParams);

  function write(changes, { replace }) {
    setSearchParams(toListParams({ ...state, ...changes }), { replace });
  }

  return {
    page: state.page,
    pageSize: state.pageSize,
    q: state.q,
    filters: state.filters,
    // ResourcesTable's sortConfig prop shape.
    sort: { column: state.sortBy, direction: state.sortOrder },

    setPage: (page) => write({ page }, { replace: false }),
    setPageSize: (pageSize) =>
      write({ pageSize, page: DEFAULT_PAGE }, { replace: false }),
    setSearch: (q) => write({ q, page: DEFAULT_PAGE }, { replace: true }),
    setSort: ({ column, direction }) =>
      write(
        { sortBy: column, sortOrder: direction, page: DEFAULT_PAGE },
        { replace: true },
      ),
    setFilters: (filters) =>
      write({ filters, page: DEFAULT_PAGE }, { replace: true }),
  };
}
