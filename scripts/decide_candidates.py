#!/usr/bin/env python
"""Fill in "decision" on every undecided group down to the --confidence tier."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from lib.candidates import (
    CANDIDATES_PATH,
    CONFIDENCE_ORDER,
    load_payload,
    member_names,
    write_payload,
)

DEFAULT_REASON = "bulk-decided by scripts/decide_candidates.py for a local rebuild"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default=str(CANDIDATES_PATH))
    parser.add_argument(
        "--confidence",
        choices=tuple(CONFIDENCE_ORDER),
        default="high",
        help="weakest tier to accept (default: high)",
    )
    parser.add_argument(
        "--decision",
        choices=("merge", "skip"),
        default="merge",
        help="what to record (default: merge)",
    )
    parser.add_argument("--reason", default=DEFAULT_REASON)
    parser.add_argument("--limit", type=int, help="cap the groups decided")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    path = Path(args.file)
    payload = load_payload(path)
    groups = payload["groups"]
    ceiling = CONFIDENCE_ORDER[args.confidence]

    already = sum(1 for group in groups if group.get("decision") is not None)
    eligible = [
        group
        for group in groups
        if group.get("decision") is None
        and CONFIDENCE_ORDER.get(group.get("confidence"), 2) <= ceiling
    ]
    if args.limit is not None:
        eligible = eligible[: args.limit]

    by_tier = Counter(group.get("confidence") for group in eligible)
    print(f"file      {path}")
    print(f"groups    {len(groups):,}")
    print(f"  already decided        {already:,}")
    print(f"  to mark '{args.decision}'{'':<12} {len(eligible):,}")
    for tier in CONFIDENCE_ORDER:
        if by_tier[tier]:
            print(f"    {tier:<20} {by_tier[tier]:,}")

    if not eligible:
        print("nothing to decide")
        return 0

    if args.dry_run:
        for group in eligible[:10]:
            names = member_names(group)
            print(f"  {group['group_id']} [{group['confidence']}] {names[:90]}")
        print(f"\n{len(eligible):,} group(s) would be decided")
        return 0

    for group in eligible:
        group["decision"] = args.decision
        group["reason"] = args.reason

    write_payload(path, payload)
    print(f"\ndecided {len(eligible):,} group(s) as '{args.decision}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
