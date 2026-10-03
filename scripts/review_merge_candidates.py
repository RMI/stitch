#!/usr/bin/env python
"""List, approve or deny merge candidates; approving mints a resource and cannot be undone."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from lib._common import dev_user, open_session
from lib.candidates import CANDIDATES_PATH, load_payload, write_payload
from stitch.api.db import merge_candidate_actions as candidates_api
from stitch.api.entities import MergeCandidateReviewRequest

COMMIT_EVERY = 500


def load_created_ids(path: Path) -> dict[int, str]:
    """Map candidate id -> group id for candidates this workflow created."""
    if not path.is_file():
        return {}
    return {
        group["created_candidate_id"]: group["group_id"]
        for group in load_payload(path)["groups"]
        if group.get("created_candidate_id")
    }


def record_status(path: Path, outcomes: dict[int, tuple[str, int | None]]) -> None:
    """Write every review outcome back into the candidates file in one pass."""
    if not path.is_file() or not outcomes:
        return
    payload = load_payload(path)
    changed = False
    for group in payload["groups"]:
        outcome = outcomes.get(group.get("created_candidate_id"))
        if outcome is not None:
            group["created_status"], group["merged_resource_id"] = outcome
            changed = True
    if changed:
        write_payload(path, payload)


async def cmd_list(session, ours: dict[int, str], mine_only: bool) -> int:
    """Print every merge candidate, or only the ones this workflow created."""
    views = await candidates_api.list_merge_candidates(session)
    if mine_only:
        views = [view for view in views if view.id in ours]

    if not views:
        print("no merge candidates", file=sys.stderr)
        return 0

    print(f"{'id':>5}  {'group':<7} {'status':<9} {'merged':>7}  resource_ids")
    for view in views:
        group = ours.get(view.id, "-")
        merged = view.merged_resource_id or "-"
        print(
            f"{view.id:>5}  {group:<7} {view.status:<9} "
            f"{str(merged):>7}  {view.resource_ids}"
        )
    print(f"\n{len(views)} candidate(s)", file=sys.stderr)
    return 0


async def cmd_review(
    session,
    user,
    action: str,
    candidate_ids: list[int],
    notes: str | None,
    path: Path,
) -> int:
    """Approve or deny each candidate, committing every COMMIT_EVERY reviews."""
    request = MergeCandidateReviewRequest(review_notes=notes) if notes else None
    if action == "approve":
        review = candidates_api.approve_merge_candidate
    else:
        review = candidates_api.deny_merge_candidate

    outcomes: dict[int, tuple[str, int | None]] = {}
    for reviewed, candidate_id in enumerate(candidate_ids, start=1):
        view = await review(
            session=session, user=user, candidate_id=candidate_id, request=request
        )
        outcomes[candidate_id] = (view.status, view.merged_resource_id)
        if reviewed % COMMIT_EVERY == 0:
            await session.commit()
            print(f"  {reviewed} {action}d", file=sys.stderr)

    await session.commit()
    record_status(path, outcomes)
    past = "approved" if action == "approve" else "denied"
    print(f"\n{past} {len(outcomes)}", file=sys.stderr)
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default=str(CANDIDATES_PATH))
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="show merge candidates")
    list_parser.add_argument(
        "--mine", action="store_true", help="only candidates created by this workflow"
    )

    for action in ("approve", "deny"):
        action_parser = sub.add_parser(action, help=f"{action} merge candidates")
        action_parser.add_argument("candidate_ids", nargs="*", type=int)
        action_parser.add_argument("--notes")
        action_parser.add_argument(
            "--all-pending",
            action="store_true",
            help=f"{action} every PENDING candidate this workflow created",
        )
        action_parser.add_argument(
            "--yes", action="store_true", help="required with --all-pending"
        )
        action_parser.add_argument(
            "--force",
            action="store_true",
            help="allow reviewing candidates this workflow did not create",
        )

    args = parser.parse_args()
    path = Path(args.file)
    ours = load_created_ids(path)

    async with open_session() as session:
        if args.command == "list":
            return await cmd_list(session, ours, args.mine)

        candidate_ids = list(args.candidate_ids)
        if args.all_pending:
            if candidate_ids:
                parser.error("give ids or --all-pending, not both")
            views = await candidates_api.list_merge_candidates(session)
            candidate_ids = [
                view.id
                for view in views
                if view.status == "PENDING" and view.id in ours
            ]
            print(
                f"--all-pending matched {len(candidate_ids)} candidate(s)",
                file=sys.stderr,
            )
            if not args.yes:
                parser.error(
                    f"--all-pending would {args.command} {len(candidate_ids)} "
                    "candidate(s) and cannot be undone; pass --yes to proceed"
                )
        if not candidate_ids:
            parser.error("no candidate ids")

        foreign = [i for i in candidate_ids if i not in ours]
        if foreign and not args.force:
            print(
                f"refusing: {len(foreign)} candidate(s) not created by this workflow "
                f"(first few: {foreign[:5]}, not in {path.name}); pass --force to override",
                file=sys.stderr,
            )
            return 1

        user = await dev_user(session)
        return await cmd_review(
            session, user, args.command, candidate_ids, args.notes, path
        )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
