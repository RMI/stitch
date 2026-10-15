"""Rebuild or repair the resource-state read model.

    python -m stitch.api.db.read_model.rebuild             # full rebuild
    python -m stitch.api.db.read_model.rebuild --if-stale  # only if not current
    python -m stitch.api.db.read_model.rebuild --ids 12 34 # repair these resources

The read model counts as ready only once a full rebuild by the same commit has
completed, so a full rebuild is needed after every deploy of new code (and after
a data restore). ``--if-stale`` is the deploy step: it rebuilds only when the
read model isn't already current for this code. ``--ids`` recomputes only the
given resources and never changes readiness.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import dispose_engine, get_engine, get_session_factory
from ..model import OGFieldResourceStateStatus, ResourceModel
from ..model.og_field_resource_state import RESOURCE_STATE_STATUS_KEY
from .state import (
    DEFAULT_BATCH_SIZE,
    ResourceStateRebuildError,
    current_code_version,
    rebuild_all_resource_state,
    rebuild_resource_state_if_stale,
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
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--ids",
        nargs="+",
        type=int,
        metavar="RESOURCE_ID",
        help="Only recompute these resource ids (safe while serving reads).",
    )
    scope.add_argument(
        "--if-stale",
        action="store_true",
        help="Do a full rebuild only if the read model isn't already built by "
        "this code (the post-deploy step). Waits for a rebuild already running, "
        "then checks again.",
    )
    parser.add_argument(
        "--batch-size",
        type=_positive_int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Resources per committed batch in a full rebuild "
        f"(default: {DEFAULT_BATCH_SIZE}).",
    )
    return parser.parse_args(argv)


async def _refuse_if_served_by_other_code(session: AsyncSession) -> None:
    """Refuse to change a table that is being served as built by other code.

    The API trusts a ready table only as built entirely by its own commit, so
    rows recomputed here by different code would be served under the wrong
    version. A table that isn't ready isn't served, and the next full rebuild
    replaces its rows. Holds a share lock on the status row, so readiness can't
    change before this transaction ends.
    """
    status = (
        await session.execute(
            select(
                OGFieldResourceStateStatus.ready,
                OGFieldResourceStateStatus.code_version,
            )
            .where(OGFieldResourceStateStatus.key == RESOURCE_STATE_STATUS_KEY)
            .with_for_update(read=True)
        )
    ).one_or_none()
    if (
        status is not None
        and status.ready
        and status.code_version != current_code_version()
    ):
        raise ResourceStateRebuildError(
            f"The read model is being served as built by code "
            f"{status.code_version}, but this is code {current_code_version()}. "
            "Run the repair from that code (or a full rebuild from this code); "
            "nothing was changed."
        )


async def _repair(
    session_factory: async_sessionmaker[AsyncSession], ids: list[int]
) -> None:
    """Recompute the given resources, refusing unknown ids (likely typos) and
    tables being served as built by other code."""
    requested = sorted(set(ids))
    async with session_factory.begin() as session:
        await _refuse_if_served_by_other_code(session)
        existing = set(
            (
                await session.scalars(
                    select(ResourceModel.id).where(ResourceModel.id.in_(requested))
                )
            ).all()
        )
        if missing := [rid for rid in requested if rid not in existing]:
            raise ResourceStateRebuildError(
                f"No resource with id(s) {missing}; nothing was changed."
            )
        recomputed = await refresh_resource_states(session, requested)
    if recomputed:
        logger.info("Recomputed resource state for ids %s.", recomputed)
    if unlisted := [rid for rid in requested if rid not in recomputed]:
        logger.info(
            "Ids %s are not listed (merged away, or no active sources), so they "
            "have no stored state; any they had was removed.",
            unlisted,
        )


async def _run(ids: list[int] | None, batch_size: int, if_stale: bool = False) -> None:
    # Outside prod the app engine echoes every statement and its parameters; for
    # a batch job over every resource that floods the logs. Progress is logged
    # per batch instead.
    get_engine().echo = False
    session_factory = get_session_factory()
    try:
        if ids:
            await _repair(session_factory, ids)
            return
        if if_stale:
            count = await rebuild_resource_state_if_stale(
                session_factory, batch_size=batch_size
            )
        else:
            count = await rebuild_all_resource_state(
                session_factory, batch_size=batch_size
            )
        if count is None:
            logger.info(
                "The read model is already built by this code (%s); nothing to do.",
                current_code_version(),
            )
        else:
            logger.info(
                "Rebuilt resource state for %d resources with code %s; the read "
                "model is ready.",
                count,
                current_code_version(),
            )
    finally:
        await dispose_engine()


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        asyncio.run(_run(args.ids, args.batch_size, args.if_stale))
    except ResourceStateRebuildError as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
