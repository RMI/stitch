"""Offline (re)build of the current-state read model.

Run after an Alembic upgrade that introduces or changes the read model, and after
any data restore::

    python -m stitch.api.db.read_model.rebuild            # full rebuild
    python -m stitch.api.db.read_model.rebuild --ids 1,2,3 # only these resources
    python -m stitch.api.db.read_model.rebuild --since 2026-09-01T00:00:00+00:00

Ongoing writes keep the model current in-band (see ``state``); this is the
"rebuildable at any time" path for bootstrapping, recovery, and targeted refreshes.
A full rebuild fully replaces the table's contents inside one transaction; the
targeted forms touch only the affected resources.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from ..config import UnitOfWork, dispose_engine, get_session_factory
from .state import (
    rebuild_all_resource_state,
    refresh_changed_since,
    refresh_resource_states,
)


def _parse_ids(raw: str) -> list[int]:
    return [int(part) for part in raw.split(",") if part.strip()]


def _parse_since(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw)
    # Compare against timezone-aware ``updated`` columns; assume UTC if naive.
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


async def _run(ids: list[int] | None, since: datetime | None) -> None:
    try:
        async with UnitOfWork(get_session_factory()) as uow:
            if ids is not None:
                await refresh_resource_states(uow.session, ids)
            elif since is not None:
                changed = list(await refresh_changed_since(uow.session, since))
                print(f"Refreshed {len(changed)} changed resource(s).")
            else:
                await rebuild_all_resource_state(uow.session)
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild the resource-state read model."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--ids",
        type=_parse_ids,
        help="Comma-separated resource ids to refresh (targeted).",
    )
    group.add_argument(
        "--since",
        type=_parse_since,
        help="ISO-8601 timestamp; refresh only resources changed after it.",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.ids, args.since))


if __name__ == "__main__":
    main()
