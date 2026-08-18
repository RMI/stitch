#!/usr/bin/env python
"""List, approve, or deny merge candidates.

Throwaway demo helper -- not shipped code, not committed.

    uv run scripts/review_merge_candidates.py list
    uv run scripts/review_merge_candidates.py list --mine
    uv run scripts/review_merge_candidates.py approve 21 22 --notes "bare vs decorated name"
    uv run scripts/review_merge_candidates.py deny 23 --notes "different reservoirs"

Approving mints a NEW resource (merged_resource_id), so scripts/data/resources.jsonl
goes stale afterwards -- re-run fetch_resources.py before searching again.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

from _common import CANDIDATES_PATH, auth_headers, base_url


def load_created_ids(path: Path) -> dict[int, str]:
    """Map candidate id -> group id for candidates this workflow created."""
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        group["created_candidate_id"]: group["group_id"]
        for group in payload.get("groups", [])
        if group.get("created_candidate_id")
    }


def record_status(path: Path, candidate_id: int, status: str, merged_id) -> None:
    """Write a review outcome back into candidates.json."""
    if not path.is_file():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for group in payload.get("groups", []):
        if group.get("created_candidate_id") == candidate_id:
            group["created_status"] = status
            group["merged_resource_id"] = merged_id
            changed = True
    if changed:
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def cmd_list(client: httpx.Client, ours: dict[int, str], mine_only: bool) -> int:
    response = client.get("/oil-gas-fields/merge-candidates", headers=auth_headers())
    response.raise_for_status()
    candidates = response.json()

    if mine_only:
        candidates = [c for c in candidates if c["id"] in ours]

    if not candidates:
        print("no merge candidates", file=sys.stderr)
        return 0

    print(f"{'id':>5}  {'group':<7} {'status':<9} {'merged':>7}  resource_ids")
    for candidate in candidates:
        group = ours.get(candidate["id"], "-")
        merged = candidate.get("merged_resource_id") or "-"
        print(
            f"{candidate['id']:>5}  {group:<7} {candidate['status']:<9} "
            f"{str(merged):>7}  {candidate['resource_ids']}"
        )
    print(f"\n{len(candidates)} candidate(s)", file=sys.stderr)
    return 0


def cmd_review(
    client: httpx.Client,
    action: str,
    candidate_ids: list[int],
    notes: str | None,
    ours: dict[int, str],
    path: Path,
    force: bool,
) -> int:
    # Guard against reviewing candidates this workflow did not create, since the
    # demo deployment is shared and approval is not obviously reversible.
    foreign = [i for i in candidate_ids if i not in ours]
    if foreign and not force:
        print(
            f"refusing: {foreign} not created by this workflow "
            f"(not in {path.name}); pass --force to override",
            file=sys.stderr,
        )
        return 1

    body = {"review_notes": notes} if notes else None
    failed = 0
    for candidate_id in candidate_ids:
        response = client.post(
            f"/oil-gas-fields/merge-candidates/{candidate_id}/{action}",
            json=body,
            headers=auth_headers(),
        )
        if response.is_success:
            candidate = response.json()
            merged = candidate.get("merged_resource_id")
            record_status(path, candidate_id, candidate["status"], merged)
            print(
                f"{candidate_id} -> {candidate['status']}"
                + (f" (merged resource {merged})" if merged else "")
            )
        else:
            failed += 1
            print(
                f"{candidate_id} -> HTTP {response.status_code} {response.text[:200]}",
                file=sys.stderr,
            )
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default=str(CANDIDATES_PATH))
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="show merge candidates")
    list_parser.add_argument(
        "--mine",
        action="store_true",
        help="only candidates created by this workflow",
    )

    for action in ("approve", "deny"):
        action_parser = sub.add_parser(action, help=f"{action} merge candidates")
        action_parser.add_argument("candidate_ids", nargs="+", type=int)
        action_parser.add_argument("--notes")
        action_parser.add_argument(
            "--force",
            action="store_true",
            help="allow reviewing candidates this workflow did not create",
        )

    args = parser.parse_args()
    path = Path(args.file)
    ours = load_created_ids(path)

    with httpx.Client(base_url=base_url(), timeout=30.0) as client:
        if args.command == "list":
            return cmd_list(client, ours, args.mine)
        return cmd_review(
            client, args.command, args.candidate_ids, args.notes, ours, path, args.force
        )


if __name__ == "__main__":
    raise SystemExit(main())
