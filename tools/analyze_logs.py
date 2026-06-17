#!/usr/bin/env python3
"""Analyze Stitch observability logs to find slow / frequent queries.

Reads the structured JSON events emitted by ``stitch.api.observability`` (one
JSON object per line) and prints two reports:

  * QUERIES  - grouped by SQL statement: how often each runs and how much total
               time it costs. The query at the top of the "total time" ranking
               is the one to optimize first (slow x frequent).
  * ROUTES   - grouped by endpoint: request latency plus how many DB queries
               each request fires (a high average is an N+1 smell).

Input is tolerant: it accepts a clean ``.jsonl`` file, raw ``docker compose
logs`` output (the ``api-1 | `` prefix is stripped), or stdin. Non-JSON lines
are ignored, so you can point it straight at mixed log output.

Examples:
    python3 tools/analyze_logs.py /tmp/stitch-events.jsonl
    docker compose logs --no-log-prefix api | python3 tools/analyze_logs.py -
    python3 tools/analyze_logs.py dump.jsonl --top 25 --sort count
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field

# Strips a leading docker-compose service prefix like "api-1  | " or "api | ".
_DOCKER_PREFIX = re.compile(r"^[a-zA-Z0-9._-]+\s*\|\s*")


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (pct in 0..100). values need not be sorted."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = max(0, min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1))))
    return ordered[rank]


def parse_events(lines) -> list[dict]:
    events: list[dict] = []
    for raw in lines:
        line = _DOCKER_PREFIX.sub("", raw.strip())
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("logger"), str):
            events.append(obj)
    return events


@dataclass
class Stat:
    key: str
    durations: list[float] = field(default_factory=list)
    # route-only extras
    db_counts: list[int] = field(default_factory=list)
    db_times: list[float] = field(default_factory=list)
    statuses: list[int] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.durations)

    @property
    def total(self) -> float:
        return sum(self.durations)

    @property
    def mean(self) -> float:
        return self.total / self.count if self.count else 0.0

    @property
    def p95(self) -> float:
        return _percentile(self.durations, 95)

    @property
    def maximum(self) -> float:
        return max(self.durations) if self.durations else 0.0


def _truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _bar(value: float, peak: float, width: int = 24) -> str:
    if peak <= 0:
        return ""
    filled = int(round((value / peak) * width))
    return "█" * filled + "·" * (width - filled)


def _print_header(title: str) -> None:
    print(f"\n{title}")
    print("=" * len(title))


def report_queries(events: list[dict], top: int, sort_key: str, width: int) -> None:
    stats: dict[str, Stat] = {}
    for e in events:
        if not e.get("logger", "").endswith(".query"):
            continue
        stmt = e.get("statement", "<none>")
        dur = float(e.get("duration_ms") or 0.0)
        stats.setdefault(stmt, Stat(stmt)).durations.append(dur)

    if not stats:
        print(
            "\n(no query events found — run with LOG_ALL_QUERIES=true or a "
            "lower SLOW_QUERY_MS to capture queries)"
        )
        return

    sorters = {
        "total": lambda s: s.total,
        "count": lambda s: s.count,
        "p95": lambda s: s.p95,
        "max": lambda s: s.maximum,
        "mean": lambda s: s.mean,
    }
    ranked = sorted(stats.values(), key=sorters[sort_key], reverse=True)
    peak_total = ranked[0].total

    _print_header(f"QUERIES — top {min(top, len(ranked))} by {sort_key}")
    print(
        f"{'count':>7} {'total_ms':>11} {'mean':>8} {'p95':>8} {'max':>8}  "
        f"{'share':<24}  statement"
    )
    print("-" * (7 + 11 + 8 + 8 + 8 + 24 + 20))
    for s in ranked[:top]:
        print(
            f"{s.count:>7} {s.total:>11.1f} {s.mean:>8.1f} {s.p95:>8.1f} "
            f"{s.maximum:>8.1f}  {_bar(s.total, peak_total):<24}  "
            f"{_truncate(s.key, width)}"
        )


def report_routes(events: list[dict], top: int, sort_key: str, width: int) -> None:
    stats: dict[str, Stat] = {}
    for e in events:
        if not e.get("logger", "").endswith(".request"):
            continue
        route = e.get("route", "<none>")
        s = stats.setdefault(route, Stat(route))
        s.durations.append(float(e.get("duration_ms") or 0.0))
        s.db_counts.append(int(e.get("db_query_count") or 0))
        s.db_times.append(float(e.get("db_time_ms") or 0.0))
        s.statuses.append(int(e.get("status_code") or 0))

    if not stats:
        print("\n(no request events found)")
        return

    def avg_db(s: Stat) -> float:
        return sum(s.db_counts) / s.count if s.count else 0.0

    sorters = {
        "total": lambda s: s.total,
        "count": lambda s: s.count,
        "p95": lambda s: s.p95,
        "max": lambda s: s.maximum,
        "mean": lambda s: s.mean,
        "queries": avg_db,
    }
    key = sorters.get(sort_key, sorters["total"])
    ranked = sorted(stats.values(), key=key, reverse=True)

    _print_header(
        f"ROUTES — top {min(top, len(ranked))} by "
        f"{sort_key if sort_key in sorters else 'total'}"
    )
    print(
        f"{'reqs':>6} {'mean_ms':>8} {'p95_ms':>8} {'max_ms':>8} "
        f"{'avg_q':>6} {'max_q':>6} {'errs':>5}  route"
    )
    print("-" * (6 + 8 + 8 + 8 + 6 + 6 + 5 + 40))
    for s in ranked[:top]:
        errs = sum(1 for c in s.statuses if c >= 500)
        flag = "  ⚠ N+1?" if avg_db(s) >= 10 else ""
        print(
            f"{s.count:>6} {s.mean:>8.1f} {s.p95:>8.1f} {s.maximum:>8.1f} "
            f"{avg_db(s):>6.1f} {max(s.db_counts, default=0):>6} {errs:>5}  "
            f"{_truncate(s.key, width)}{flag}"
        )


def summarize(events: list[dict]) -> None:
    reqs = [e for e in events if e.get("logger", "").endswith(".request")]
    queries = [e for e in events if e.get("logger", "").endswith(".query")]
    times = sorted(e["ts"] for e in events if e.get("ts"))
    _print_header("SUMMARY")
    print(f"events parsed : {len(events)}")
    print(f"requests      : {len(reqs)}")
    print(f"queries logged: {len(queries)}")
    if times:
        print(f"time range    : {times[0]}  ->  {times[-1]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("path", help="JSONL file, or '-' for stdin")
    parser.add_argument("--top", type=int, default=15, help="rows per report")
    parser.add_argument(
        "--sort",
        default="total",
        choices=["total", "count", "p95", "max", "mean", "queries"],
        help="ranking metric (queries=avg DB queries/request, routes only)",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=90,
        help="max characters for statement/route column",
    )
    parser.add_argument("--queries-only", action="store_true")
    parser.add_argument("--routes-only", action="store_true")
    args = parser.parse_args(argv)

    if args.path == "-":
        events = parse_events(sys.stdin)
    else:
        with open(args.path, encoding="utf-8") as fh:
            events = parse_events(fh)

    if not events:
        print("No events found. Is this a stitch observability log?", file=sys.stderr)
        return 1

    summarize(events)
    if not args.routes_only:
        report_queries(events, args.top, args.sort, args.width)
    if not args.queries_only:
        route_sort = args.sort
        report_routes(events, args.top, route_sort, args.width)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
