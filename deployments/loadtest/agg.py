#!/usr/bin/env python3
"""Aggregate tagged observability events into a clean branch x endpoint table.

Reads stitch observability JSONL (request + query events) whose `scenario` field
is `b=<branch>;vol=<vol>;perm=<perm>;ep=<ep>`. Emits per-cell request latency and
per-query-name timings, so main/290/291 sit side by side without label truncation.

Usage:
    python3 agg.py <file-or-dir> [--perm all8] [--vol 1k] [--b 290] [--ep list]
                                 [--out results/table.txt] [--csv results/table.csv]

Results:
    Prints the tables to stdout. With --out, also writes the same text to a file;
    with --csv, writes a machine-readable request-latency CSV. Both create parent
    dirs. This is where persisted timing results go (see README "Results layout").
"""

from __future__ import annotations
import csv as _csv
import json
import math
import sys
import statistics
from pathlib import Path
from collections import defaultdict
import re

_PREFIX = re.compile(r"^[a-zA-Z0-9._-]+\s*\|\s*")


def pct(xs, q):
    if not xs:
        return 0.0
    s = sorted(xs)
    r = min(max(math.ceil(q / 100 * len(s)), 1), len(s))
    return s[r - 1]


def parse_scen(scen):
    d = {}
    for part in (scen or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            d[k] = v
    return d


def load(path):
    p = Path(path)
    files = sorted(p.glob("*.jsonl")) if p.is_dir() else [p]
    for f in files:
        for line in f.read_text(errors="ignore").splitlines():
            line = _PREFIX.sub("", line.strip())
            if not line.startswith("{"):
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if isinstance(o, dict) and isinstance(o.get("logger"), str):
                yield o


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    src = args[0]
    want, out, csv_out = {}, None, None
    for k in ("perm", "vol", "b", "ep"):
        if f"--{k}" in args:
            want[k] = args[args.index(f"--{k}") + 1]
    if "--out" in args:
        out = args[args.index("--out") + 1]
    if "--csv" in args:
        csv_out = args[args.index("--csv") + 1]

    req = defaultdict(list)
    dbq = defaultdict(list)
    dbt = defaultdict(list)
    qn = defaultdict(list)

    for e in load(src):
        scen = parse_scen(e.get("scenario"))
        if not scen:
            continue
        if any(scen.get(k) != v for k, v in want.items()):
            continue
        key = (scen.get("b"), scen.get("vol"), scen.get("perm"), scen.get("ep"))
        lg = e.get("logger", "")
        if lg.endswith(".request"):
            if isinstance(e.get("duration_ms"), (int, float)):
                req[key].append(e["duration_ms"])
            if isinstance(e.get("db_query_count"), (int, float)):
                dbq[key].append(e["db_query_count"])
            if isinstance(e.get("db_time_ms"), (int, float)):
                dbt[key].append(e["db_time_ms"])
        elif lg.endswith(".query"):
            qkey = key + (e.get("query_name") or "(unlabeled)",)
            if isinstance(e.get("duration_ms"), (int, float)):
                qn[qkey].append(e["duration_ms"])

    lines: list[str] = []

    def emit(s=""):
        lines.append(s)

    emit("=== REQUEST latency (ms) ===")
    hdr = f"{'ep':<16}{'branch':<7}{'perm':<9}{'vol':<6}{'n':>4}{'mean':>8}{'med':>8}{'p95':>8}{'dbq':>5}{'dbms':>8}"
    emit(hdr)
    emit("-" * len(hdr))
    for key in sorted(req, key=lambda k: (k[3] or "", k[0] or "")):
        b, vol, perm, ep = key
        d = req[key]
        emit(
            f"{ep or '?':<16}{b or '?':<7}{perm or '?':<9}{vol or '?':<6}{len(d):>4}"
            f"{statistics.mean(d):>8.1f}{statistics.median(d):>8.1f}{pct(d, 95):>8.1f}"
            f"{(statistics.mean(dbq[key]) if dbq[key] else 0):>5.1f}"
            f"{(statistics.mean(dbt[key]) if dbt[key] else 0):>8.1f}"
        )

    emit("")
    emit("=== QUERY latency by query_name (ms, mean) ===")
    hdr2 = f"{'ep':<16}{'branch':<7}{'perm':<9}{'query_name':<34}{'n':>5}{'mean':>8}{'p95':>8}"
    emit(hdr2)
    emit("-" * len(hdr2))
    for qkey in sorted(
        qn, key=lambda k: (k[3] or "", k[0] or "", -statistics.mean(qn[k]))
    ):
        b, vol, perm, ep, name = qkey
        d = qn[qkey]
        if statistics.mean(d) < 0.5:
            continue
        emit(
            f"{ep or '?':<16}{b or '?':<7}{perm or '?':<9}{name[:33]:<34}{len(d):>5}"
            f"{statistics.mean(d):>8.2f}{pct(d, 95):>8.2f}"
        )

    text = "\n".join(lines)
    print(text)

    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text + "\n")
        print(f"\n[agg] wrote table -> {out}")
    if csv_out:
        Path(csv_out).parent.mkdir(parents=True, exist_ok=True)
        with open(csv_out, "w", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(
                [
                    "ep",
                    "branch",
                    "perm",
                    "vol",
                    "n",
                    "mean_ms",
                    "median_ms",
                    "p95_ms",
                    "avg_db_queries",
                    "avg_db_ms",
                ]
            )
            for key in sorted(req, key=lambda k: (k[3] or "", k[0] or "")):
                b, vol, perm, ep = key
                d = req[key]
                w.writerow(
                    [
                        ep,
                        b,
                        perm,
                        vol,
                        len(d),
                        round(statistics.mean(d), 2),
                        round(statistics.median(d), 2),
                        round(pct(d, 95), 2),
                        round(statistics.mean(dbq[key]), 2) if dbq[key] else 0,
                        round(statistics.mean(dbt[key]), 2) if dbt[key] else 0,
                    ]
                )
        print(f"[agg] wrote csv   -> {csv_out}")


if __name__ == "__main__":
    main()
