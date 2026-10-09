"""Rebuild or repair the resource-state read model.

    python -m stitch.api.db.read_model.rebuild             # full rebuild
    python -m stitch.api.db.read_model.rebuild --ids 12 34 # repair these resources

A full rebuild is a required step after deploying the migration that creates the
read model (and after a coalescing-logic change or data restore). Until it
completes, list reads use live coalescing. ``--ids`` recomputes only the given
resources and is safe to run while the read model is serving reads.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence

from ..config import dispose_engine, get_session_factory
from .state import (
    DEFAULT_BATCH_SIZE,
    rebuild_all_resource_state,
    refresh_resource_states,
)

logger = logging.getLogger(__name__)


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return value


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild the resource-state read model, or repair specific "
        "resources."
    )
    parser.add_argument(
        "--ids",
        nargs="+",
        type=int,
        metavar="RESOURCE_ID",
        help="Only recompute these resource ids (safe while serving reads).",
    )
    parser.add_argument(
        "--batch-size",
        type=_positive_int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Resources per committed batch in a full rebuild "
        f"(default: {DEFAULT_BATCH_SIZE}).",
    )
    return parser.parse_args(argv)


async def _run(ids: list[int] | None, batch_size: int) -> None:
    session_factory = get_session_factory()
    try:
        if ids:
            async with session_factory.begin() as session:
                await refresh_resource_states(session, ids)
            logger.info("Recomputed resource state for ids %s.", sorted(set(ids)))
        else:
            count = await rebuild_all_resource_state(
                session_factory, batch_size=batch_size
            )
            logger.info(
                "Rebuilt resource state for %d resources; the read model is ready.",
                count,
            )
    finally:
        await dispose_engine()


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(_run(args.ids, args.batch_size))


if __name__ == "__main__":
    main()
