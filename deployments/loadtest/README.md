# Load testing

Measure and **compare HTTP response-time distributions between runs/PRs** for the
stitch API. The pieces:

- **k6** (`grafana/k6`) drives load against the read-heavy `oil-gas-fields`
  endpoints and produces the aggregate stats (p90/p95/p99, RPS, error rate).
- **Prometheus** stores every run, tagged `testid=<git-sha>` (k6 streams metrics
  in via remote-write).
- **Grafana** (http://localhost:3001) renders the **k6 — PR response-time
  comparison** dashboard, which overlays the `testid`s you select.
- **Jaeger** (http://localhost:16686, from the `full` profile) is the
  qualitative drill-down: once a run shows a p95 regression, open a slow trace
  to see *where* the time went. k6/Prometheus tell you *that* it regressed;
  Jaeger tells you *why*.

All of this lives in `docker-compose.observability.yml` under the `loadtest`
profile (Prometheus/Grafana/k6) and the `full` profile (OTel collector +
Jaeger).

## Files

| Path | Purpose |
| --- | --- |
| `script.js` | k6 scenario: weighted mix of read-only GETs with randomized params. |
| `prometheus.yml` | Prometheus config (remote-write receiver enabled via CLI flag). |
| `grafana/provisioning/` | Auto-wires the Prometheus datasource (uid `stitch-prom`) and the dashboard provider. |
| `grafana/dashboards/k6-pr-compare.json` | The comparison dashboard. |

## Usage

1. **Seed a realistic dataset.** Bump `SEED_FAKER_POST_COUNT` in `.env` (e.g.
   `5000`) so the ILIKE search / pagination / coalesced-CTE paths have real data.
   Seeding is reproducible (`RANDOM_SEED=8675309`).

2. **Bring up the stack** (app + tracing + Prometheus + Grafana, persistent):

   ```sh
   make loadtest-stack
   ```

3. **Run a load test.** Each run is tagged with `TESTID` (defaults to the
   current short git SHA):

   ```sh
   make loadtest                 # testid = current git short SHA
   make loadtest TESTID=pr143    # or label it yourself
   ```

   k6 prints its end-of-test summary and streams metrics to Prometheus.

4. **Compare runs.** Open Grafana at http://localhost:3001, go to the **k6 — PR
   response-time comparison** dashboard, and select the `testid`s to compare in
   the dropdown. Each selected run shows up as its own bar (p95/p99/avg latency,
   total requests, failure rate) plus a per-endpoint p95 table.

   To compare PRs, repeat this per branch — but **do not** re-run
   `make loadtest-stack` each time: it rebuilds everything and re-runs the
   seed, which grows the dataset and makes later branches look slower. Instead:

   ```sh
   # (switch to the branch you want to test)
   make loadtest-rebuild        # rebuild only the API + run migrations, no reseed
   make loadtest                # tagged with that branch's git short SHA
   ```

   `loadtest-rebuild` leaves the DB and the Prometheus/Grafana history intact,
   so every branch is tested against an identical dataset. The Prometheus volume
   lives outside the `clean-docker` chain, so prior runs survive rebuilds.
   (Re-running on the same commit reuses its SHA as `testid` and overwrites that
   run — pass `TESTID=<label>` to keep a distinct data point.)

   If a branch has **conflicting migrations** and needs a clean DB, wipe only
   the database volume (keeps the Grafana/Prometheus history), then bring the
   stack back up to re-migrate + reseed:

   ```sh
   make loadtest-reset-db       # down + `docker volume rm <project>_db_data`
   make loadtest-stack          # fresh DB, this branch's migrations, reseed
   make loadtest
   ```

5. **Tear down** (keeps the Prometheus/Grafana history volumes):

   ```sh
   make loadtest-down
   ```

> **Never** use `make clean-docker` or `down --volumes` mid-comparison — both
> drop *all* volumes, including `*_prom_data` / `*_grafana_data`, erasing your
> run history. Use `make loadtest-reset-db` (DB only) instead.

## Tuning

`.env` knobs (read by the `k6` service): `K6_VUS`, `K6_DURATION`, `K6_RATE`,
`K6_BASE_URL`, `GF_SECURITY_ADMIN_PASSWORD`. The scenario uses a
`constant-arrival-rate` executor — `K6_RATE` is requests/sec, `K6_VUS` the
preallocated virtual users. Thresholds in `script.js` are informational, not yet
a CI gate.
