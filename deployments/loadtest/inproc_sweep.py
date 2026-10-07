"""In-process permission-profile latency sweep (token-free).

Runs INSIDE the api container: imports the running branch's FastAPI app, overrides
the auth dependency to inject arbitrary permission sets, and drives the read
endpoints via httpx ASGITransport, timing each request end-to-end. This lets us
compare the permission profiles with no Auth0 tokens — useful for any branch family
whose reads are permission-filtered by `source:read:<src>` scopes.

Usage (inside container):
    python /tmp/inproc_sweep.py <branch-label> <n_measure> [n_warmup]
Prints one JSON object per (profile, endpoint) to stdout: latency stats in ms.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time

import httpx

from stitch.api.main import app
from stitch.api.auth import get_token_claims
from stitch.auth.claims import TokenClaims
from stitch.auth.permissions import RESOURCE_READ, source_read_permission

# The 8 OGSI source keys. `public6` = everything a baseline (public) user can see;
# the two restricted keys (wm, ccr) are the ones that vary by grant in this app.
SOURCES = ["rmi", "gem", "wm", "llm", "ccr", "bc", "alb", "nor"]
PUBLIC6 = ["rmi", "gem", "llm", "bc", "alb", "nor"]  # all except wm, ccr


def perms(*sources: str) -> frozenset[str]:
    return frozenset({RESOURCE_READ, *(source_read_permission(s) for s in sources)})


# Edit this map for a different branch family's permission profiles. `zero` and the
# 3-source set are useful edge cases (empty result path; a partial grant that probes
# any read-model fallback path).
PROFILES: dict[str, frozenset[str]] = {
    "all8": perms(*SOURCES),
    "public6": perms(*PUBLIC6),
    "wm": perms(*PUBLIC6, "wm"),
    "ccr": perms(*PUBLIC6, "ccr"),
    "zero": perms(),  # resource:read only -> empty result set
    "partial3": perms("gem", "llm", "rmi"),  # partial grant (fallback-path probe)
}


def claims_for(p: frozenset[str]) -> TokenClaims:
    return TokenClaims(
        sub="perf|inproc", email="perf@example.com", name="Perf", permissions=p, raw={}
    )


def percentile(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    import math

    r = min(max(math.ceil(q / 100 * len(s)), 1), len(s))
    return s[r - 1]


async def main() -> None:
    branch = sys.argv[1] if len(sys.argv) > 1 else "?"
    n_measure = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    n_warmup = int(sys.argv[3]) if len(sys.argv) > 3 else 10

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://inproc", timeout=60.0
    ) as client:
        # Resolve a sample id once (all8) for id/detail/sources endpoints.
        app.dependency_overrides[get_token_claims] = lambda: claims_for(
            PROFILES["all8"]
        )
        r = await client.get(
            "/api/v1/oil-gas-fields/", params={"page": 1, "page_size": 1}
        )
        rid = None
        if r.status_code == 200:
            items = r.json().get("items") or []
            rid = items[0]["id"] if items else None

        def endpoints() -> list[tuple[str, str, dict]]:
            eps = [
                ("list", "/api/v1/oil-gas-fields/", {"page": 1, "page_size": 50}),
                (
                    "list_ps200",
                    "/api/v1/oil-gas-fields/",
                    {"page": 1, "page_size": 200},
                ),
                (
                    "list_sort",
                    "/api/v1/oil-gas-fields/",
                    {"page": 1, "page_size": 50, "sort_by": "name"},
                ),
                (
                    "list_q",
                    "/api/v1/oil-gas-fields/",
                    {"page": 1, "page_size": 50, "q": "field"},
                ),
                ("filter_options", "/api/v1/oil-gas-fields/filter-options", {}),
            ]
            if rid is not None:
                eps += [
                    ("id", f"/api/v1/oil-gas-fields/{rid}", {}),
                    ("detail", f"/api/v1/oil-gas-fields/{rid}/detail", {}),
                    (
                        "field_sources",
                        f"/api/v1/oil-gas-fields/{rid}/fields/name/sources",
                        {},
                    ),
                ]
            return eps

        for profile, pset in PROFILES.items():
            app.dependency_overrides[get_token_claims] = lambda p=pset: claims_for(p)
            for ep, path, params in endpoints():
                for _ in range(n_warmup):
                    await client.get(path, params=params)
                lat: list[float] = []
                codes: set[int] = set()
                for _ in range(n_measure):
                    t0 = time.perf_counter()
                    resp = await client.get(path, params=params)
                    lat.append((time.perf_counter() - t0) * 1000.0)
                    codes.add(resp.status_code)
                print(
                    json.dumps(
                        {
                            "branch": branch,
                            "profile": profile,
                            "ep": ep,
                            "n": len(lat),
                            "codes": sorted(codes),
                            "mean_ms": round(statistics.mean(lat), 2),
                            "median_ms": round(statistics.median(lat), 2),
                            "p95_ms": round(percentile(lat, 95), 2),
                            "max_ms": round(max(lat), 2),
                        }
                    )
                )
    app.dependency_overrides.clear()


if __name__ == "__main__":
    asyncio.run(main())
