// k6 load test for the stitch API: read-only GET endpoints on oil-gas-fields.
//
// Exercises the read-heavy, query-expensive paths (ILIKE search + paginated
// coalesced-CTE listing, filter-options DISTINCT scans, single-resource and
// detail lookups) with a weighted mix of randomized parameters. Metrics stream
// to Azure Monitor managed Prometheus via remote-write (configured by the
// run-perf workflow's env). Each run is tagged at invocation with
// `--tag pr=<N> --tag run_id=<gh run id> --tag sha=<short sha>` plus a
// self-labeling composite `--tag run=pr<N>-<run_id>`, so the Grafana
// "k6 — PR response-time comparison" dashboard can both compare across PRs
// (select several $pr) and watch a single PR evolve across runs (select $run).
//
// Tunables (env): BASE_URL, K6_VUS, K6_DURATION, K6_RATE, BEARER_TOKEN.
// Note: no console.log — forbidden-patterns CI rejects it; use check() instead.

import http from "k6/http";
import { check, group } from "k6";
import { Counter } from "k6/metrics";

const BASE_URL = (__ENV.BASE_URL || "http://api:8000").replace(/\/$/, "");
const API = `${BASE_URL}/api/v1`;
const VUS = Number(__ENV.K6_VUS) || 20;
const RATE = Number(__ENV.K6_RATE) || 50;
const DURATION = __ENV.K6_DURATION || "1m";

// AUTH_DISABLED=true (local default) needs no header; send one only if provided.
const HEADERS = __ENV.BEARER_TOKEN
  ? { Authorization: `Bearer ${__ENV.BEARER_TOKEN}` }
  : {};

const SORTABLE = [
  "name",
  "basin",
  "region",
  "country",
  "discovery_year",
  "field_status",
];
const FILTER_FIELDS = [
  "basin",
  "region",
  "country",
  "field_status",
  "location_type",
  "primary_hydrocarbon_group",
];
const SOURCES = ["rmi", "gem", "wm", "llm"];

const setupFailures = new Counter("setup_failures");

export const options = {
  scenarios: {
    reads: {
      executor: "constant-arrival-rate",
      rate: RATE,
      timeUnit: "1s",
      duration: DURATION,
      preAllocatedVUs: VUS,
      maxVUs: VUS * 4,
    },
  },
  thresholds: {
    // Only fail the run on actual errors. Latency is what we measure and
    // compare in Grafana, not a pass/fail gate (a crossed threshold makes k6
    // exit 99, which would fail the load-test step). Promote latency to a gate
    // later by adding e.g. "http_req_duration{kind:list}": ["p(95)<800"].
    http_req_failed: ["rate<0.05"],
  },
};

function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

// Pull a page of real ids + search terms so detail/search hit live data
// regardless of how many rows were seeded.
export function setup() {
  const res = http.get(`${API}/oil-gas-fields/?page_size=100`, {
    headers: HEADERS,
    tags: { name: "setup" },
  });
  if (res.status !== 200) {
    setupFailures.add(1);
    return { ids: [], terms: [] };
  }
  const items = (res.json("items") || []);
  const ids = items.map((it) => it.id).filter((id) => id !== undefined);
  const terms = [];
  for (const it of items) {
    const d = it.data || {};
    for (const v of [d.name, d.basin, d.region]) {
      if (typeof v === "string" && v.length >= 3) {
        terms.push(v.slice(0, 4));
      }
    }
  }
  return { ids, terms };
}

function listRequest(data) {
  const params = [
    `page=${1 + Math.floor(Math.random() * 5)}`,
    `page_size=${pick([25, 50, 100])}`,
    `sort_by=${pick(SORTABLE)}`,
    `sort_order=${pick(["asc", "desc"])}`,
  ];
  // ~60% of list calls include a search term (the ILIKE path).
  if (data.terms.length && Math.random() < 0.6) {
    params.push(`q=${encodeURIComponent(pick(data.terms))}`);
  }
  if (Math.random() < 0.3) {
    params.push(`source=${pick(SOURCES)}`);
  }
  const res = http.get(`${API}/oil-gas-fields/?${params.join("&")}`, {
    headers: HEADERS,
    tags: { name: "list", kind: "list" },
  });
  check(res, { "list 200": (r) => r.status === 200 });
}

function filterOptionsRequest() {
  const res = http.get(
    `${API}/oil-gas-fields/filter-options?field=${pick(FILTER_FIELDS)}`,
    { headers: HEADERS, tags: { name: "filter-options", kind: "filter" } },
  );
  check(res, { "filter-options 200": (r) => r.status === 200 });
}

function detailRequest(data) {
  if (!data.ids.length) {
    return;
  }
  const id = pick(data.ids);
  const detail = Math.random() < 0.5;
  const path = detail
    ? `${API}/oil-gas-fields/${id}/detail`
    : `${API}/oil-gas-fields/${id}`;
  const res = http.get(path, {
    headers: HEADERS,
    tags: { name: detail ? "detail" : "by-id", kind: "detail" },
  });
  check(res, { "detail 2xx": (r) => r.status === 200 });
}

export default function (data) {
  // Weighted mix: list searches dominate, then detail lookups, then filters.
  const roll = Math.random();
  if (roll < 0.55) {
    group("list", () => listRequest(data));
  } else if (roll < 0.85) {
    group("detail", () => detailRequest(data));
  } else {
    group("filter-options", () => filterOptionsRequest());
  }
}
