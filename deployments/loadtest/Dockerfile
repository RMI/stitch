# k6 image for the stitch API: load test (script.js) + seeder (seed.js).
#
# k6 runs JS on goja, which has no npm at runtime, so the faker-based seeder is
# bundled to a single file with esbuild in a Node build stage. script.js uses
# only k6 built-ins, so it ships as-is. Build context is the repo root, matching
# the other deployment images.
#
# ENTRYPOINT is `k6 run`; the caller picks the script + flags, e.g.
#   docker run <img> /scripts/script.js    --out experimental-prometheus-rw --tag pr=1
#   docker run <img> /scripts/seed.dist.js --tag pr=1

# ── bundle stage: faker + seed.js -> one goja-friendly file ──────────────
FROM node:20-alpine AS bundle
WORKDIR /build
COPY deployments/loadtest/package.json ./
RUN npm install --no-audit --no-fund
COPY deployments/loadtest/seed.js ./seed.js
COPY deployments/loadtest/data ./data
RUN npm run build

# ── runtime stage: k6 with both scripts ─────────────────────────────────
FROM grafana/k6:0.54.0
COPY deployments/loadtest/script.js /scripts/script.js
COPY --from=bundle /build/seed.dist.js /scripts/seed.dist.js
ENTRYPOINT ["k6", "run"]
