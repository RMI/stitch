/**
 * URL schema for the Merge Review queue.
 *
 * Same contract as the resources list (config/listParams.js): the query string
 * is a complete serialization of the queue view, loading a URL reproduces it
 * for any user, and the param names mirror what the API takes, so there is no
 * translation layer. See the "Merge review URLs" section of the frontend README
 * before changing them.
 *
 * Rules:
 * - Defaults are omitted, so the default view (pending candidates, newest
 *   first, page 1, no search) is a bare /merge-candidate-review.
 * - Serialization order is fixed, so the same view always produces the same URL.
 * - Junk is tolerated, never fatal: an unknown status is dropped, and a
 *   malformed page, page_size or sort falls back to its default.
 * - The default status filter is PENDING, so "no status param" cannot also
 *   mean "every status". Selecting nothing is written as `status=all`.
 */
import { DEFAULT_PAGE, PAGE_SIZE_OPTIONS } from "../queries/resources";

export const MERGE_STATUSES = ["PENDING", "APPROVED", "DENIED"];
export const DEFAULT_STATUSES = ["PENDING"];
const ALL_STATUSES = "all";

export const DEFAULT_QUEUE_PAGE_SIZE = 25;

// Each option is one sort_by + sort_order pair the API accepts, labelled in
// plain language. The first is the default.
export const QUEUE_SORT_OPTIONS = [
  {
    key: "newest",
    label: "Newest first",
    sortBy: "created",
    sortOrder: "desc",
  },
  { key: "oldest", label: "Oldest first", sortBy: "created", sortOrder: "asc" },
  {
    key: "recently-reviewed",
    label: "Recently reviewed",
    sortBy: "reviewed_at",
    sortOrder: "desc",
  },
  {
    key: "earliest-reviewed",
    label: "Earliest reviewed",
    sortBy: "reviewed_at",
    sortOrder: "asc",
  },
];
const DEFAULT_SORT = QUEUE_SORT_OPTIONS[0];

function parsePage(raw) {
  const value = Number(raw);
  return /^\d+$/.test(raw ?? "") && Number.isSafeInteger(value) && value >= 1
    ? value
    : DEFAULT_PAGE;
}

function parsePageSize(raw) {
  const value = Number(raw);
  return PAGE_SIZE_OPTIONS.includes(value) ? value : DEFAULT_QUEUE_PAGE_SIZE;
}

// [] means "every status". Returned in MERGE_STATUSES order.
function parseStatuses(rawValues) {
  if (rawValues.includes(ALL_STATUSES)) return [];
  const statuses = MERGE_STATUSES.filter((status) =>
    rawValues.includes(status),
  );
  return statuses.length ? statuses : DEFAULT_STATUSES;
}

// sort_by and sort_order are a unit; an unknown pair falls back to the default.
function parseSort(rawSortBy, rawSortOrder) {
  return (
    QUEUE_SORT_OPTIONS.find(
      (option) =>
        option.sortBy === rawSortBy && option.sortOrder === rawSortOrder,
    ) ?? DEFAULT_SORT
  );
}

function isDefaultStatuses(statuses) {
  return (
    statuses.length === DEFAULT_STATUSES.length &&
    DEFAULT_STATUSES.every((status) => statuses.includes(status))
  );
}

export function parseMergeReviewParams(searchParams) {
  return {
    page: parsePage(searchParams.get("page")),
    pageSize: parsePageSize(searchParams.get("page_size")),
    q: (searchParams.get("q") ?? "").trim(),
    statuses: parseStatuses(searchParams.getAll("status")),
    sortKey: parseSort(
      searchParams.get("sort_by"),
      searchParams.get("sort_order"),
    ).key,
  };
}

export function toMergeReviewParams({ page, pageSize, q, statuses, sortKey }) {
  const params = new URLSearchParams();
  if (page > DEFAULT_PAGE) params.set("page", String(page));
  if (pageSize !== DEFAULT_QUEUE_PAGE_SIZE) {
    params.set("page_size", String(pageSize));
  }

  const trimmedSearch = (q ?? "").trim();
  if (trimmedSearch) params.set("q", trimmedSearch);

  if (statuses.length === 0) {
    params.set("status", ALL_STATUSES);
  } else if (!isDefaultStatuses(statuses)) {
    for (const status of MERGE_STATUSES) {
      if (statuses.includes(status)) params.append("status", status);
    }
  }

  const sort = QUEUE_SORT_OPTIONS.find((option) => option.key === sortKey);
  if (sort && sort !== DEFAULT_SORT) {
    params.set("sort_by", sort.sortBy);
    params.set("sort_order", sort.sortOrder);
  }

  return params;
}

// The list endpoint's query params for a parsed view. An empty status list
// sends no status filter, which the API reads as every status.
export function toMergeCandidateQuery({
  page,
  pageSize,
  q,
  statuses,
  sortKey,
}) {
  const sort =
    QUEUE_SORT_OPTIONS.find((option) => option.key === sortKey) ?? DEFAULT_SORT;
  return {
    page,
    page_size: pageSize,
    q: q || undefined,
    status: statuses.length ? statuses : undefined,
    sort_by: sort.sortBy,
    sort_order: sort.sortOrder,
  };
}
