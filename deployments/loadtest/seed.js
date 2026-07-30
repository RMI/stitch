// k6 seeder for the stitch API — replaces the old Python `stitch-seed` service.
//
// Populates a deployed (or local) API with two kinds of data, all via
// POST /oil-gas-fields/:
//   1. the committed demo files in ./data/*.json (merge / llm / source-value
//      demos) — bundled at build time, so they exercise those specific paths;
//   2. `SEED_VOLUME` faker-generated fields, for realistic row counts so the
//      load test's query-expensive paths (ILIKE search, coalesced-CTE list)
//      behave like production.
//
// faker is an npm module; k6 runs on goja (not Node), so this file is BUNDLED
// with esbuild in the Docker build (see Dockerfile). Generation is reproducible:
// each field index is produced from `faker.seed(SEED_RANDOM_SEED + index)`, so
// the same index yields the same field regardless of which VU runs it.
//
// POSTs are tagged (name=create, kind=create, phase=seed) and — when the seed
// step streams to remote-write — show up in the Grafana write-path panels
// alongside the read load test, keyed by the same pr/run tags.
//
// Env: BASE_URL, BEARER_TOKEN, SEED_VOLUME, SEED_VUS, SEED_RANDOM_SEED, SEED_RUN_ID.
// Note: no console.log — forbidden-patterns CI rejects it; use check() instead.

import http from "k6/http";
import { check, sleep } from "k6";
import exec from "k6/execution";
import { faker } from "@faker-js/faker/locale/en";

import f001 from "./data/001.json";
import f002 from "./data/002.json";
import f003 from "./data/003-mock-data.json";
import f004 from "./data/004-merge-demo.json";
import f005 from "./data/005-llm-demo.json";
import f006 from "./data/006-source-values-demo.json";

const BASE_URL = (__ENV.BASE_URL || "http://api:8000").replace(/\/$/, "");
const API = `${BASE_URL}/api/v1`;

// Read a numeric env var, honoring an explicit 0 (a plain `|| default` would
// treat 0 as unset — so SEED_VOLUME=0 must fall through here, not to the default).
function envNum(name, def) {
  const raw = __ENV[name];
  if (raw === undefined || raw === "") return def;
  const n = Number(raw);
  return Number.isNaN(n) ? def : n;
}

const VOLUME = envNum("SEED_VOLUME", 500);
const VUS = envNum("SEED_VUS", 10);
const SEED = envNum("SEED_RANDOM_SEED", 8675309);
const RUN_ID = __ENV.SEED_RUN_ID || "local";
const PRODUCER = "stitch-loadtest-seed/1.0";

const HEADERS = {
  "Content-Type": "application/json",
  ...(__ENV.BEARER_TOKEN ? { Authorization: `Bearer ${__ENV.BEARER_TOKEN}` } : {}),
};

// Enum domains — mirror packages/stitch-ogsi/.../model/types.py.
const LOCATION_TYPE = ["Onshore", "Offshore", "Unknown"];
const CONVENTIONALITY = ["Conventional", "Unconventional", "Mixed", "Unknown"];
const HYDROCARBON = [
  "Ultra-Light Oil", "Light Oil", "Medium Oil", "Heavy Oil", "Extra-Heavy Oil",
  "Dry Gas", "Wet Gas", "Acid Gas", "Condensate", "Mixed", "Unknown",
];
const FIELD_STATUS = ["Producing", "Non-Producing", "Abandoned", "Planned"];
const SOURCES = ["gem", "wm", "rmi", "llm", "ccr"];
const NULL_PROB = 0.3;

// Flatten every committed data file (each is an array of payloads) into one list.
const STATIC = [].concat(f001, f002, f003, f004, f005, f006);
const TOTAL = STATIC.length + VOLUME;

export const options = {
  scenarios: {
    seed: {
      executor: "shared-iterations",
      vus: VUS,
      iterations: TOTAL,
      maxDuration: "10m",
    },
  },
  thresholds: {
    // A broken seed should fail the CI step.
    http_req_failed: ["rate<0.05"],
  },
};

function clone(obj) {
  return JSON.parse(JSON.stringify(obj));
}

function maybe(fn) {
  return faker.number.float() < NULL_PROB ? null : fn();
}

// Attach a source_record to each source in a payload (the API expects it; the
// old Python seeder injected the same shape in payloads._attach_source_record).
function withSourceRecord(payload, recordPrefix, kind) {
  const p = clone(payload);
  const sources = Array.isArray(p.source_data) ? p.source_data : [];
  sources.forEach((source, idx) => {
    const original = clone(source);
    source.source_record = {
      record_id: `${recordPrefix}:${idx + 1}`,
      run_id: RUN_ID,
      observed_at: new Date().toISOString(),
      producer: PRODUCER,
      payload: { kind, source: original, source_index: idx + 1 },
    };
  });
  return p;
}

// Build one reproducible faker field for a given index.
function buildFakerPayload(index) {
  faker.seed(SEED + index);
  const discovery = faker.number.int({ min: 1800, max: 2090 });
  const productionStart = Math.min(2100, discovery + faker.number.int({ min: 0, max: 20 }));
  const fid = Math.min(2100, productionStart + faker.number.int({ min: 0, max: 10 }));
  const withYears = faker.number.float() >= 0.1;

  const source = {
    source: faker.helpers.arrayElement(SOURCES),
    name: `${faker.company.name().replace(/,/g, "")} ${faker.helpers.arrayElement(["Field", "Oil Field", "Gas Field", "Asset"])}`,
    country: faker.location.countryCode("alpha-3"),
    latitude: maybe(() => faker.location.latitude()),
    longitude: maybe(() => faker.location.longitude()),
    name_local: maybe(() => faker.lorem.words({ min: 1, max: 3 })),
    state_province: maybe(() => faker.location.state()),
    region: maybe(() => faker.location.city()),
    basin: maybe(() => `${faker.lorem.word()} Basin`),
    reservoir_formation: maybe(() => `${faker.lorem.word()} Formation`),
    location_type: maybe(() => faker.helpers.arrayElement(LOCATION_TYPE)),
    production_conventionality: maybe(() => faker.helpers.arrayElement(CONVENTIONALITY)),
    primary_hydrocarbon_group: maybe(() => faker.helpers.arrayElement(HYDROCARBON)),
    field_status: maybe(() => faker.helpers.arrayElement(FIELD_STATUS)),
    discovery_year: withYears ? discovery : null,
    production_start_year: withYears ? productionStart : null,
    fid_year: withYears ? fid : null,
  };

  return withSourceRecord(
    { id: 0, source_data: [source], constituents: [] },
    `faker:${index}`,
    "seed_faker",
  );
}

export function setup() {
  // Seed runs before the load-test warm-up, so wait for the API to be healthy.
  for (let i = 0; i < 30; i++) {
    const res = http.get(`${API}/health`, { headers: HEADERS, tags: { name: "health" } });
    if (res.status === 200) return;
    sleep(3);
  }
}

export default function () {
  const i = exec.scenario.iterationInTest;
  let payload;
  if (i < STATIC.length) {
    payload = withSourceRecord(STATIC[i], `static:${i + 1}`, "seed_static");
  } else {
    payload = buildFakerPayload(i - STATIC.length);
  }
  const res = http.post(`${API}/oil-gas-fields/`, JSON.stringify(payload), {
    headers: HEADERS,
    tags: { name: "create", kind: "create", phase: "seed" },
  });
  check(res, { "create 2xx": (r) => r.status >= 200 && r.status < 300 });
}
