#!/usr/bin/env python3
"""Consolidate in-process sweep results into a comparison table + CSV.

Reads the `logs/inproc-<branch>.results.jsonl` files produced by
`inproc_sweep.py` (one JSON object per branch/profile/endpoint) and prints a
per-endpoint profile x branch median-latency table with speedup vs a baseline
branch. With --csv, writes a machine-readable file.

Usage:
    python3 sweep_table.py logs/inproc-*.results.jsonl [--baseline main]
                                                        [--csv results/sweep.csv]
"""

from __future__ import annotations
import csv as _csv
import json
import sys
from pathlib import Path

EP_ORDER = [
    "list",
    "list_ps200",
    "list_sort",
    "list_q",
    "filter_options",
    "id",
    "detail",
    "field_sources",
]
PROF_ORDER = ["all8", "public6", "wm", "ccr", "partial3", "zero"]


def main():
    args = sys.argv[1:]
    baseline = args[args.index("--baseline") + 1] if "--baseline" in args else "main"
    csv_out = args[args.index("--csv") + 1] if "--csv" in args else None
    # Positional files = args that are neither a flag nor a flag's value.
    flag_value_idx = set()
    for flag in ("--baseline", "--csv"):
        if flag in args:
            flag_value_idx.add(args.index(flag) + 1)
    files = [
        a
        for i, a in enumerate(args)
        if not a.startswith("--") and i not in flag_value_idx
    ]
    if not files:
        print(__doc__)
        return

    med = {}  # (ep, branch, profile) -> median_ms
    branches = set()
    for f in files:
        for line in Path(f).read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if "median_ms" not in r:
                continue
            med[(r["ep"], r["branch"], r["profile"])] = r["median_ms"]
            branches.add(r["branch"])

    others = [b for b in sorted(branches) if b != baseline]
    lines = []
    for ep in EP_ORDER:
        if not any((ep, b, p) in med for b in branches for p in PROF_ORDER):
            continue
        lines.append(f"\n=== {ep}: in-process median ms by profile ===")
        head = f"  {'profile':<9}{baseline:>9}" + "".join(f"{b:>9}" for b in others)
        head += "".join(f"{b + 'x':>8}" for b in others)
        lines.append(head)
        for p in PROF_ORDER:
            base = med.get((ep, baseline, p))
            if base is None:
                continue
            row = f"  {p:<9}{base:>9}"
            for b in others:
                row += f"{med.get((ep, b, p), float('nan')):>9}"
            for b in others:
                v = med.get((ep, b, p))
                row += f"{(base / v):>7.1f}x" if v else f"{'-':>8}"
            lines.append(row)
    text = "\n".join(lines)
    print(text)

    if csv_out:
        Path(csv_out).parent.mkdir(parents=True, exist_ok=True)
        with open(csv_out, "w", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(
                ["ep", "profile", "branch", "median_ms", f"speedup_vs_{baseline}"]
            )
            for ep in EP_ORDER:
                for p in PROF_ORDER:
                    base = med.get((ep, baseline, p))
                    for b in sorted(branches):
                        v = med.get((ep, b, p))
                        if v is None:
                            continue
                        sp = (
                            round(base / v, 2) if (base and v and b != baseline) else ""
                        )
                        w.writerow([ep, p, b, v, sp])
        print(f"\n[sweep] wrote csv -> {csv_out}")


if __name__ == "__main__":
    main()
