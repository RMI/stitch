# k6 load-generator image for the stitch API.
#
# Thin layer over the official grafana/k6 image: it only bakes in our test
# script. The base image's entrypoint is already `k6`; we extend it to
# `k6 run /scripts/script.js` so callers append ONLY flags
# (e.g. `--out experimental-prometheus-rw --tag pr=123`) and never re-type `k6`
# (the double-`k6 k6 run` foot-gun). Build context is the repo root, matching
# the other deployment images.
FROM grafana/k6:0.54.0

COPY deployments/loadtest/script.js /scripts/script.js

ENTRYPOINT ["k6", "run", "/scripts/script.js"]
