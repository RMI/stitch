/**
 * Reads and writes the Merge Review queue view state from the URL.
 *
 * Mirrors useListState: the URL is the single source of truth, and every
 * setter round-trips the complete state through the schema
 * (config/mergeReviewParams.js). Refining the view (search, statuses, sort) rewrites
 * the current history entry; paging pushes, so Back steps through pages.
 * Page size is not remembered across visits, unlike the resources list.
 */
import { useMemo } from "react";
import { useSearchParams } from "react-router";
import {
  parseMergeReviewParams,
  toMergeReviewParams,
} from "../config/mergeReviewParams";
import { DEFAULT_PAGE } from "../queries/resources";

export function useMergeReviewState() {
  const [searchParams, setSearchParams] = useSearchParams();
  const state = parseMergeReviewParams(searchParams);

  // Built once per setSearchParams, so callers (the page's step-back effect)
  // can depend on them. Each write reads the URL it changes rather than this
  // render's state, so two quick writes can't overwrite each other.
  const setters = useMemo(() => {
    function write(changes, { replace }) {
      setSearchParams(
        (current) =>
          toMergeReviewParams({
            ...parseMergeReviewParams(current),
            ...changes,
          }),
        { replace },
      );
    }

    return {
      // `replace` is for corrections the reviewer did not ask for (stepping
      // back from a page past the end), which should not add a Back step.
      setPage: (page, { replace = false } = {}) => write({ page }, { replace }),
      setPageSize: (pageSize) =>
        write({ pageSize, page: DEFAULT_PAGE }, { replace: false }),
      setStatuses: (statuses) =>
        write({ statuses, page: DEFAULT_PAGE }, { replace: true }),
      setSortKey: (sortKey) =>
        write({ sortKey, page: DEFAULT_PAGE }, { replace: true }),
      setSearch: (q) => write({ q, page: DEFAULT_PAGE }, { replace: true }),
    };
  }, [setSearchParams]);

  return { ...state, ...setters };
}
