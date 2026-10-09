# Read-perf comparison harness

Branch-agnostic tooling to compare DB read-performance across a **baseline branch and
one or more candidate branches**, over a data-volume ladder and the API's permission
profiles, plus a response-consistency check. Pairs with the deterministic complexity
knobs in `deployments/seed`. Builds on the observability stack in
[`../PERFORMANCE.md`](../PERFORMANCE.md) and [`../../tools/analyze_logs.py`](../../tools/analyze_logs.py).

Nothing here is specific to a particular feature branch — point it at whatever family
of branches you want to compare.

## What's here

| File | Purpose |
|---|---|
| `driver.sh` | Single-stream HTTP load driver. Warms up then fires measured, `X-Stitch-Perf-Scenario`-tagged requests at the read endpoints (override the endpoint set with `EPS_FILE`). |
| `agg.py` | Reads observability JSONL → per-`(branch,vol,perm,ep)` request latency + per-`query_name` timings. `--out`/`--csv` persist. |
| `sweep_table.py` | Consolidates `inproc_sweep.py` results into a per-endpoint profile×branch table with speedups vs a baseline. |
| `inproc_sweep.py` | Token-free permission sweep **inside the api container** (ASGITransport + auth-dependency override). Edit `PROFILES` for your branch family. |
| `capture.sh` | Captures normalized JSON responses per endpoint/profile for the consistency check (strips `run_id`/`observed_at`). |
| `diff_consistency.sh` | Diffs captured responses of each candidate branch against a baseline (both configurable). |

All scripts are parameterized by env/args — no hardcoded branch names or paths.

## Comparable datasets (seed complexity knobs)

The seeder (`../seed`) is extended with deterministic knobs (off by default → legacy
single-source behavior). Set them in `.env`; with a fixed `RANDOM_SEED` (compose pins
`8675309`) every branch seeds an equivalent dataset (only `source_record`
`run_id`/`observed_at` differ, normalized out of consistency diffs):

```bash
SEED_FAKER_POST_COUNT=1000      # volume rung
SEED_ALL_SOURCE_KEYS=true       # span all 8 OGSI source keys (adds ccr/alb/bc/nor)
SEED_MULTI_SOURCE_PROB=0.5      # fraction of resources with multiple sources
SEED_MAX_EXTRA_SOURCES=3        # up to 1+N sources on a multi-source resource
SEED_OVERRIDE_PROB=0.15         # fraction getting a field-priority override (PUT)
SEED_MERGE_PROB=0.04            # fraction drawn into merges (merge-candidate approve)
SEED_START_INDEX=0              # cumulative-seeding offset (see below)
```

### Cumulative (rung-by-rung) seeding

`SEED_START_INDEX` grows a volume one rung at a time without re-seeding from scratch.
A run with `SEED_START_INDEX=K` build-and-discards the first `K` faker payloads (so the
RNG advances identically) and emits indices `K+1 .. K+count`, byte-identical (modulo
`run_id`/`observed_at`) to indices `K+1 .. K+count` of a fresh `count=K+count` run — so
the volume stays deterministic and nested. Static payloads emit only at `K=0`. Example
ladder (1k → 10k → 50k), re-running `seed` against the same volume each step:

```bash
SEED_START_INDEX=0     SEED_FAKER_POST_COUNT=1000   # base rung
SEED_START_INDEX=1000  SEED_FAKER_POST_COUNT=9000   # -> 10k
SEED_START_INDEX=10000 SEED_FAKER_POST_COUNT=40000  # -> 50k
```

> These knobs live in `deployments/seed`; the branches you compare must carry that
> extension (merge it to `main`, or apply it onto each branch before seeding).

## Per-branch run procedure (local docker)

Run one branch's stack at a time (they share host ports). From a worktree checked out at
the branch, with `.env` present (copy the repo-root `.env`), `AUTH_DISABLED=true` for
token-free runs, and the seed knobs above:

```bash
C="docker compose -f docker-compose.yml -f docker-compose.local.yml"

# 1. Fresh stack (wipes this project's volume), build, wait for a healthy api.
$C --profile "*" down --volumes --remove-orphans
$C --profile full up -d --build --wait api        # --wait guarantees the host port bind

# 2. Seed the dataset (one-shot; --no-deps so it doesn't recreate api).
$C run --rm --no-deps seed
#    Cumulative ladder: re-run with SEED_START_INDEX / SEED_FAKER_POST_COUNT bumped.

# 3. OPTIONAL per-branch warm/build hook — e.g. a branch that maintains a derived
#    table may want a one-time rebuild here (and you can time it). No-op otherwise.

# 4. Drive HTTP load (AUTH_DISABLED all-8, or TOKEN=... for a real permission profile).
BASE=http://localhost:8000/api/v1 BRANCH=<label> VOL=1k PERM=all8 \
  WARMUP=10 MEASURE=60 ./driver.sh

# 5. Capture logs for the aggregator.
$C logs --no-log-prefix api | grep -a 'b=<label>;vol=1k' > logs/<label>-1k-all8.jsonl

# 6. Token-free permission sweep (inside the container).
$C cp inproc_sweep.py api:/tmp/inproc_sweep.py
$C exec -T api python /tmp/inproc_sweep.py <label> 60 10 \
  | grep '"mean_ms"' | grep -v '"logger"' > logs/inproc-<label>.results.jsonl

# 7. Consistency capture.
BASE=http://localhost:8000/api/v1 BRANCH=<label> PERM=all8 OUTDIR=consistency ./capture.sh

# 8. Free the port before the next branch.
$C --profile "*" stop && docker stop <project>-api-1
```

Then analyze across all branches (the aggregator keys on the scenario tag, not branch
names, so any set of labels works):

```bash
python3 agg.py logs --perm all8 --out results/http-1k-all8.txt --csv results/http-1k-all8.csv
python3 sweep_table.py logs/inproc-*.results.jsonl --baseline main --csv results/inproc-1k.csv
./diff_consistency.sh consistency main        # baseline main; candidates auto-detected
python3 ../../tools/analyze_logs.py logs/*.jsonl --group-by scenario
```

## Auth options

- **`AUTH_DISABLED=true`** (dev only) — every request runs as an all-sources dev user;
  simplest for the all-8 profile and for seeding when no valid token is at hand.
- **Real bearer tokens** — pass `TOKEN=...` to `driver.sh`/`capture.sh` to measure a
  specific permission profile over the real HTTP path.
- **In-process sweep** — `inproc_sweep.py` needs no tokens; it injects arbitrary
  permission sets by overriding the auth dependency against the real Postgres.

## Gotchas (learned the hard way)

- `docker compose stop` **skips profiled services**; stop the api explicitly
  (`docker stop <project>-api-1`) or `--profile "*" stop` to release host ports.
- `run --rm --no-deps seed` avoids recreating the api container (a plain
  `up --force-recreate seed` cascades into the api and can hit a port conflict,
  leaving the api created **without** its host port binding — use `up --wait api`).
- With `LOG_ALL_QUERIES=true` the seed writes flood the log; the aggregator filters by
  scenario and seed traffic is untagged, so it's excluded from comparisons.
- Single-stream medians across one pass are directional (~5–10%), not CI-grade; for
  tighter numbers raise `MEASURE` and/or run repeated passes tagged with a `rep=` label.
