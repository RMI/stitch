#!/usr/bin/env python
"""Create merge candidates, one per reviewed group.

    uv run --package stitch-api python scripts/create_merge_candidate.py 12 4013
    uv run --package stitch-api python scripts/create_merge_candidate.py --from-file --dry-run
    uv run --package stitch-api python scripts/create_merge_candidate.py --from-file --limit 20

Calls `merge_candidate_actions.create_merge_candidate` directly against a
session. No HTTP.

In --from-file mode this creates every group in scripts/data/candidates.json
whose "decision" is "merge", and records the result back into that file. Re-runs
skip groups that already succeeded, so it is safe to run repeatedly.

Creating only stages a PENDING candidate; nothing is merged until it is
approved (see review_merge_candidates.py).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from lib._common import CANDIDATES_PATH, dev_user, open_session
from stitch.api.db import merge_candidate_actions as candidates
from stitch.api.entities import (
    MergeCandidateCreateRequest,
    MergeCandidateView,
    User,
)


async def create_one(
    session: AsyncSession, user: User, resource_ids: list[int]
) -> MergeCandidateView:
    """Stage one PENDING candidate. Caller commits."""
    return await candidates.create_merge_candidate(
        session=session,
        user=user,
        request=MergeCandidateCreateRequest(resource_ids=resource_ids),
    )


async def run_ids(resource_ids: list[int]) -> int:
    async with open_session() as session:
        user = await dev_user(session)
        view = await create_one(session, user, resource_ids)
        await session.commit()
    print(view.model_dump_json(indent=2))
    return 0


def write_payload(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


async def run_from_file(
    path: Path, *, dry_run: bool, limit: int | None, checkpoint_every: int
) -> int:
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
            names = " || ".join(member["name"] or "" for member in group["members"])
            print(f"{group['group_id']} {group['resource_ids']}  {names}")
        print(f"\n{len(pending)} group(s) would be created", file=sys.stderr)
        return 0

    async with open_session() as session:
        user = await dev_user(session)
        for created, group in enumerate(pending, start=1):
            view = await create_one(session, user, group["resource_ids"])
            group["created_candidate_id"] = view.id
            group["created_status"] = view.status

            # Commit and checkpoint on the same boundary. Re-serializing this
            # file costs ~163ms at a few thousand groups, against ~6ms of
            # database work per create -- doing it per create is what made a
            # 7,912-group run spend 21 of its 24 minutes writing JSON.
            if created % checkpoint_every == 0:
                await session.commit()
                write_payload(path, payload)
                print(f"  {created} created", file=sys.stderr)

        await session.commit()
        write_payload(path, payload)

    print(f"\ncreated {len(pending)}", file=sys.stderr)
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resource_ids", nargs="*", type=int)
    parser.add_argument("--from-file", nargs="?", const=str(CANDIDATES_PATH))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=100,
        help="rewrite candidates.json after this many creates (default 100)",
    )
    args = parser.parse_args()

    if args.from_file:
        return await run_from_file(
            Path(args.from_file),
            dry_run=args.dry_run,
            limit=args.limit,
            checkpoint_every=args.checkpoint_every,
        )
    if len(args.resource_ids) < 2:
        parser.error("give at least two resource ids, or use --from-file")
    return await run_ids(args.resource_ids)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
