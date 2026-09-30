"""STIT-763 baseline: time the CURRENT per-field `filter_options`, and diff it.

Calls the real `stitch.api.db.og_field_resource_actions.filter_options` once per
field, which is what the Resource List page does today, and diffs its values
against the one-query spike. Direct session calls, no HTTP.

    # default: every licence profile, diffed
    uv run --package stitch-api python scripts/stit763_options_baseline.py

    # one ad-hoc source set, with timings
    uv run --package stitch-api python scripts/stit763_options_baseline.py \
        --sources wm,ccr --runs 5

LICENCE PROFILES

wm and ccr are the only licensed sources; read access to bc, alb, gem, llm and
rmi is universal. So a real user holds one of four source sets, and the options
they see must be identical between the spike and the current implementation for
every one of them. Licensing is applied BEFORE coalescing, so it changes which
value wins a field, not just which rows are visible -- that is why parity has to
be checked per profile rather than inferred from the all-sources case.

The run also reports whether the profiles differ FROM EACH OTHER. If they did
not, "identical" would prove nothing: it would only mean licensing had no effect
on this corpus.

Where the time goes: each `filter_options` call rebuilds and re-scans the whole
coalescing core (memberships x values x priorities, plus the override outer
join) and re-runs the window sort, then keeps one field's winners. The ranking
already partitions by (resource_id, colname), so eight calls repeat the same
scan eight times. That is the cost the spike removes, and it lives in the
action, not here.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections.abc import Collection
from statistics import mean

from sqlalchemy.ext.asyncio import AsyncSession

from _common import open_session
from stit763_options_spike import FIELDS, fetch_options
from stitch.api.db import og_field_resource_actions as actions
from stitch.api.entities import OGFieldFilterOptionsParams

# Universal read access, no licence required.
OPEN_SOURCES = ("bc", "alb", "gem", "llm", "rmi")

# The four source sets a real user can hold.
PROFILES: dict[str, tuple[str, ...]] = {
    "open (no licence)": OPEN_SOURCES,
    "open + wm": OPEN_SOURCES + ("wm",),
    "open + ccr": OPEN_SOURCES + ("ccr",),
    "open + wm + ccr": OPEN_SOURCES + ("wm", "ccr"),
}

# The six the UI renders today, a subset of the spike's eight. Used only to
# reproduce the ticket's per-page-load figure.
UI_FIELDS = (
    "country",
    "region",
    "state_province",
    "basin",
    "field_status",
    "primary_hydrocarbon_group",
)

# Built once, so the timed region measures the query rather than pydantic
# validating the same eight field names on every run.
PARAMS = {field: OGFieldFilterOptionsParams(field=field) for field in FIELDS}


async def baseline_options(
    session: AsyncSession, sources: Collection[str] | None
) -> dict[str, list[str]]:
    """The current implementation's answer: one call per field."""
    return {
        field: await actions.filter_options(session, PARAMS[field], sources)
        for field in FIELDS
    }


def diff(baseline: dict[str, list[str]], spike: dict[str, list[str]]) -> list[str]:
    """Value-level differences per field. Empty means identical."""
    problems = []
    for field in FIELDS:
        baseline_values = set(baseline[field])
        spike_values = set(spike[field])
        missing = sorted(baseline_values - spike_values)
        extra = sorted(spike_values - baseline_values)

        if missing or extra:
            report = f"{field}: {len(missing)} missing, {len(extra)} extra"
            if missing:
                report += f"\n      missing: {missing[:8]}"
            if extra:
                report += f"\n      extra:   {extra[:8]}"
            problems.append(report)
        elif baseline[field] != spike[field]:
            problems.append(f"{field}: same values, different order")
    return problems


async def run_profiles() -> int:
    fingerprints: dict[str, tuple] = {}
    failures = 0

    async with open_session() as session:
        for label, sources in PROFILES.items():
            baseline = await baseline_options(session, sources)
            spike = await fetch_options(session, sources)
            problems = diff(baseline, spike)
            total = sum(len(v) for v in baseline.values())
            counts = " ".join(
                f"{f.split('_')[0][:6]}={len(baseline[f])}" for f in FIELDS
            )

            print(f"\n{label}")
            print(f"  sources: {','.join(sources)}")
            print(f"  options: {total} values   {counts}")
            if problems:
                failures += 1
                print("  DIFFERS:")
                for problem in problems:
                    print(f"    {problem}")
            else:
                print("  spike == current: identical")

            fingerprints[label] = tuple(tuple(baseline[f]) for f in FIELDS)

    print("\ndo the profiles differ from each other?")
    labels = list(fingerprints)
    distinct = len(set(fingerprints.values()))
    for i, a in enumerate(labels):
        for b in labels[i + 1 :]:
            same = fingerprints[a] == fingerprints[b]
            print(f"  {a:<18} vs {b:<18} {'SAME' if same else 'differ'}")
    print(f"  {distinct} distinct answer(s) across {len(labels)} profiles")
    if distinct == 1:
        print("  WARNING: licensing changes nothing here, so parity proves little")

    print()
    if failures:
        print(f"FAIL: {failures} profile(s) differ between spike and current")
        return 1
    print(f"PASS: identical across all {len(PROFILES)} licence profiles")
    return 0


async def run_timed(sources: list[str], runs: int) -> int:
    async with open_session() as session:
        print(f"sources: {','.join(sources)}")

        await baseline_options(session, sources)  # warm-up, not timed

        per_field: dict[str, list[float]] = {field: [] for field in FIELDS}
        baseline: dict[str, list[str]] = {}
        for _ in range(runs):
            for field in FIELDS:
                start = time.perf_counter()
                baseline[field] = await actions.filter_options(
                    session, PARAMS[field], sources
                )
                per_field[field].append((time.perf_counter() - start) * 1000)

        spike = await fetch_options(session, sources)

    means = {field: mean(per_field[field]) for field in FIELDS}

    print(f"\ncurrent per-field `filter_options`, mean of {runs} runs, ms")
    for field in FIELDS:
        marker = "*" if field in UI_FIELDS else " "
        print(f" {marker} {field:<28} {means[field]:8.1f}")

    ui_total = sum(means[field] for field in UI_FIELDS)
    all_total = sum(means.values())
    print(f"\n  6 calls (* = what the page loads today) {ui_total:8.1f}")
    print(f"  8 calls (like-for-like vs the spike)    {all_total:8.1f}")

    problems = diff(baseline, spike)
    print("\ndiff: spike vs current")
    if problems:
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("  identical")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5, help="timed runs (default 5)")
    parser.add_argument(
        "--sources",
        default=None,
        help="ad-hoc comma-separated source set; omit to run every licence profile",
    )
    args = parser.parse_args()

    if args.sources is None:
        return await run_profiles()
    return await run_timed(args.sources.split(","), args.runs)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
