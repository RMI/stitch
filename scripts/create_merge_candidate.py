#!/usr/bin/env python
"""Create merge candidates, either from ids on the command line or from a file.

Throwaway demo helper -- not shipped code, not committed.

    uv run scripts/create_merge_candidate.py 7 8
    uv run scripts/create_merge_candidate.py --from-file --dry-run
    uv run scripts/create_merge_candidate.py --from-file --limit 3

In --from-file mode this posts every group in scripts/data/candidates.json whose
"decision" is "merge", and records the API's answer back into that file. Re-runs
skip groups that already succeeded, so it is safe to run repeatedly.

Target and credentials come from .env (STITCH_API_BASE_URL,
STITCH_CLIENT_PRIVILEGED_BEARER_TOKEN); see scripts/_common.py.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from stitch.client import AsyncStitchClient, StitchAPIError

from _common import CANDIDATES_PATH, auth_headers, base_url


def build_client() -> AsyncStitchClient:
    headers = auth_headers()
    return AsyncStitchClient(
        base_url=base_url(),
        timeout=30.0,
        headers_provider=lambda: headers,
    )


async def post_one(client: AsyncStitchClient, resource_ids: list[int]) -> dict:
    """POST a single group. Returns {"candidate": ...} or {"error": ...}."""
    try:
        return {"candidate": await client.create_merge_candidate(resource_ids)}
    except StitchAPIError as exc:
        # 400 is the API's fingerprint de-dupe: a candidate for this exact id set
        # already exists (pending, approved, or denied). Expected on a re-run.
        if exc.status_code == 400:
            return {"error": "already exists", "status_code": 400}
        return {
            "error": str(exc),
            "status_code": exc.status_code,
            "body": exc.response_text,
        }


async def run_ids(resource_ids: list[int]) -> int:
    async with build_client() as client:
        result = await post_one(client, resource_ids)
    if "candidate" in result:
        print(json.dumps(result["candidate"], indent=2))
        return 0
    print(f"failed: {result['error']}", file=sys.stderr)
    if result.get("status_code") == 403:
        print(
            "hint: the token is missing the 'merge-candidate:create' permission",
            file=sys.stderr,
        )
    return 1


async def run_from_file(path: Path, *, dry_run: bool, limit: int | None) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    groups = payload["groups"]

    pending = [
        group
        for group in groups
        if group.get("decision") == "merge" and not group.get("created_candidate_id")
    ]
    undecided = sum(1 for group in groups if group.get("decision") is None)
    if undecided:
        print(f"note: {undecided} group(s) still undecided", file=sys.stderr)

    if limit is not None:
        pending = pending[:limit]

    if not pending:
        print("nothing to create", file=sys.stderr)
        return 0

    if dry_run:
        for group in pending:
            names = " || ".join(m["name"] or "" for m in group["members"])
            print(f"{group['group_id']} {group['resource_ids']}  {names}")
        print(f"\n{len(pending)} group(s) would be created", file=sys.stderr)
        return 0

    created = failed = 0
    async with build_client() as client:
        for group in pending:
            result = await post_one(client, group["resource_ids"])
            if "candidate" in result:
                group["created_candidate_id"] = result["candidate"]["id"]
                group["created_status"] = result["candidate"]["status"]
                group.pop("created_error", None)
                created += 1
                print(
                    f"{group['group_id']} -> candidate {group['created_candidate_id']}"
                )
            else:
                group["created_error"] = result["error"]
                failed += 1
                print(
                    f"{group['group_id']} -> {result['error']}",
                    file=sys.stderr,
                )
            # Persist after every call so an interruption cannot lose the id of
            # a candidate that was already created server-side.
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    print(f"\ncreated {created}, failed {failed}", file=sys.stderr)
    return 1 if failed and not created else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resource_ids", nargs="*", type=int)
    parser.add_argument("--from-file", nargs="?", const=str(CANDIDATES_PATH))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.from_file:
        if args.resource_ids:
            parser.error("pass resource ids or --from-file, not both")
        return asyncio.run(
            run_from_file(Path(args.from_file), dry_run=args.dry_run, limit=args.limit)
        )

    if len(args.resource_ids) < 2:
        parser.error("need at least 2 resource ids, or --from-file")
    return asyncio.run(run_ids(args.resource_ids))


if __name__ == "__main__":
    raise SystemExit(main())
