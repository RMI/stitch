/**
 * URL schema for the resources list view.
 *
 * The query string is a complete serialization of the list view: filters, sort,
 * search, and pagination. Loading a URL reproduces the same view for any user,
 * so these param names are a stable contract — see the "List view URLs" section
 * of the frontend README before changing them.
 *
 * The schema deliberately mirrors what `queries/api.js` sends to the API, so
 * there is no translation layer to keep in sync.
 *
 * The functions here are pure. The module imports its allowlists rather than
 * restating them, so adding a sortable column or a page size cannot drift the
 * URL schema. Those live in non-component modules (config/listColumns.js,
 * queries/resources.js) so no file has to export both a component and shared
 * constants — doing so breaks Fast Refresh.
 *
 * Rules:
 * - Defaults are omitted, so the default view is a bare `/`.
 * - Serialization order is fixed, so the same view always produces the same URL.
 * - Junk in the params this module owns is tolerated, never fatal: page,
 *   page_size, sort_by and sort_order all fall back to their defaults.
 * - Filter values are passed through unvalidated, because the set of valid
 *   values is server-side data this module cannot see. An unknown value for a
 *   free-text filter (country, region, state_province, basin) simply matches
 *   nothing; for the enum-backed ones (field_status,
 *   primary_hydrocarbon_group) the API rejects it with a 422, so a
 *   hand-edited URL can surface an error rather than an empty list.
 * - Params we do not own are ignored on read and dropped on the next write.
 * - Page size alone has a second fallback: the size the user chose earlier in
 *   the session (config/pageSizePreference.js), passed in as
 *   `fallbackPageSize`. It applies only when the URL has no valid
 *   `page_size`, so a URL always wins. Because a URL without `page_size`
 *   therefore opens at the *viewer's* remembered size, `page_size` is written
 *   into every URL that carries any other state (a page, search, sort or
 *   filter) -- page=3 at 50 per page is different rows from page=3 at 10.
 *   It is omitted only from an otherwise bare URL whose size matches the
 *   fallback, so a bare "/" means "the list at my page size".
 */
import { FILTER_FIELDS } from "./filters";
import { SORTABLE_COLUMN_KEYS } from "./listColumns";
import {
  DEFAULT_PAGE,
  DEFAULT_PAGE_SIZE,
  PAGE_SIZE_OPTIONS,
} from "../queries/resources";

const FILTER_KEYS = FILTER_FIELDS.map((field) => field.key);
const SORT_ORDERS = ["asc", "desc"];
const DEFAULT_SORT_ORDER = "asc";

function parsePage(raw) {
  const value = Number(raw);
  return /^\d+$/.test(raw ?? "") && Number.isSafeInteger(value) && value >= 1
    ? value
    : DEFAULT_PAGE;
}

function parsePageSize(raw, fallbackPageSize) {
  const value = Number(raw);
  return PAGE_SIZE_OPTIONS.includes(value) ? value : fallbackPageSize;
}

// sort_by and sort_order are a unit: a lone order has no meaning, and an
// unsortable column would 422 at the API, so both are dropped together.
function parseSort(rawSortBy, rawSortOrder) {
  if (!SORTABLE_COLUMN_KEYS.includes(rawSortBy)) {
    return { sortBy: null, sortOrder: DEFAULT_SORT_ORDER };
  }
  return {
    sortBy: rawSortBy,
    sortOrder: SORT_ORDERS.includes(rawSortOrder)
      ? rawSortOrder
      : DEFAULT_SORT_ORDER,
  };
}

export function parseListParams(
  searchParams,
  { fallbackPageSize = DEFAULT_PAGE_SIZE } = {},
) {
  const filters = {};
  for (const key of FILTER_KEYS) {
    filters[key] = searchParams.getAll(key).filter((value) => value !== "");
  }

  return {
    page: parsePage(searchParams.get("page")),
    pageSize: parsePageSize(searchParams.get("page_size"), fallbackPageSize),
    q: (searchParams.get("q") ?? "").trim(),
    ...parseSort(searchParams.get("sort_by"), searchParams.get("sort_order")),
    filters,
  };
}

export function toListParams(
  { page, pageSize, q, sortBy, sortOrder, filters },
  { fallbackPageSize = DEFAULT_PAGE_SIZE } = {},
) {
  const params = new URLSearchParams();
  const trimmedSearch = (q ?? "").trim();
  const hasFilters = FILTER_KEYS.some((key) =>
    (filters?.[key] ?? []).some((value) => value !== ""),
  );
  const hasOtherState =
    page > DEFAULT_PAGE ||
    Boolean(trimmedSearch) ||
    Boolean(sortBy) ||
    hasFilters;

  if (page > DEFAULT_PAGE) params.set("page", String(page));
  if (
    pageSize &&
    (hasOtherState ||
      pageSize !== DEFAULT_PAGE_SIZE ||
      pageSize !== fallbackPageSize)
  ) {
    params.set("page_size", String(pageSize));
  }

  if (trimmedSearch) params.set("q", trimmedSearch);

  if (sortBy) {
    params.set("sort_by", sortBy);
    params.set("sort_order", sortOrder ?? DEFAULT_SORT_ORDER);
  }

  for (const key of FILTER_KEYS) {
    for (const value of filters?.[key] ?? []) {
      if (value !== "") params.append(key, value);
    }
  }

  return params;
}
