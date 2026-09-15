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
 * Rules:
 * - Defaults are omitted, so the default view is a bare `/`.
 * - Serialization order is fixed, so the same view always produces the same URL.
 * - Junk is tolerated, never fatal: a hand-edited URL renders a sane list.
 * - Params we do not own are ignored on read and dropped on the next write.
 */
import { FILTER_FIELDS } from "./filters";
import { PAGE_SIZE_OPTIONS } from "../components/Pagination";
import { SORTABLE_COLUMN_KEYS } from "../components/ResourcesTable";
import { DEFAULT_PAGE, DEFAULT_PAGE_SIZE } from "../queries/resources";

const FILTER_KEYS = FILTER_FIELDS.map((field) => field.key);
const SORT_ORDERS = ["asc", "desc"];
const DEFAULT_SORT_ORDER = "asc";

function parsePage(raw) {
  const value = Number(raw);
  return Number.isInteger(value) && value >= 1 ? value : DEFAULT_PAGE;
}

function parsePageSize(raw) {
  const value = Number(raw);
  return PAGE_SIZE_OPTIONS.includes(value) ? value : DEFAULT_PAGE_SIZE;
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

export function parseListParams(searchParams) {
  const filters = {};
  for (const key of FILTER_KEYS) {
    filters[key] = searchParams.getAll(key).filter((value) => value !== "");
  }

  return {
    page: parsePage(searchParams.get("page")),
    pageSize: parsePageSize(searchParams.get("page_size")),
    q: (searchParams.get("q") ?? "").trim(),
    ...parseSort(searchParams.get("sort_by"), searchParams.get("sort_order")),
    filters,
  };
}

export function toListParams({
  page,
  pageSize,
  q,
  sortBy,
  sortOrder,
  filters,
}) {
  const params = new URLSearchParams();

  if (page && page !== DEFAULT_PAGE) params.set("page", String(page));
  if (pageSize && pageSize !== DEFAULT_PAGE_SIZE) {
    params.set("page_size", String(pageSize));
  }

  const trimmedSearch = (q ?? "").trim();
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
