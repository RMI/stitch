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
 *
 * Page size is also remembered for the session, and stands in for the default
 * when the URL has none -- so the Resources tab and logotype, which link to a
 * bare "/", keep the size the user picked. The URL still wins when it has one.
 */
import { useSearchParams } from "react-router";
import { parseListParams, toListParams } from "../config/listParams";
import {
  getRememberedPageSize,
  rememberPageSize,
} from "../config/pageSizePreference";
import { DEFAULT_PAGE, DEFAULT_PAGE_SIZE } from "../queries/resources";

export function useListState() {
  const [searchParams, setSearchParams] = useSearchParams();
  const fallbackPageSize = getRememberedPageSize() ?? DEFAULT_PAGE_SIZE;
  const state = parseListParams(searchParams, { fallbackPageSize });

  function write(changes, { replace }, options = { fallbackPageSize }) {
    setSearchParams(toListParams({ ...state, ...changes }, options), {
      replace,
    });
  }

  return {
    page: state.page,
    pageSize: state.pageSize,
    q: state.q,
    filters: state.filters,
    // ResourcesTable's sortConfig prop shape.
    sort: { column: state.sortBy, direction: state.sortOrder },

    setPage: (page) => write({ page }, { replace: false }),
    // The only place a page size is remembered: a deliberate choice, not
    // whatever a shared link happened to contain.
    setPageSize: (pageSize) => {
      rememberPageSize(pageSize);
      write(
        { pageSize, page: DEFAULT_PAGE },
        { replace: false },
        { fallbackPageSize: getRememberedPageSize() ?? DEFAULT_PAGE_SIZE },
      );
    },
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
