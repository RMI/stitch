"""Offline rebuild of the current-state read model.

Run once after an Alembic upgrade that introduces or changes the read model, and
after any data restore::

    python -m stitch.api.db.read_model.rebuild

Ongoing writes keep the model current in-band (see ``state``); this is the
"rebuildable at any time" path for bootstrapping and recovery. Safe to re-run --
it fully replaces the table's contents inside one transaction.
"""

from __future__ import annotations

import asyncio

from ..config import UnitOfWork, dispose_engine, get_session_factory
from .state import rebuild_all_resource_state


async def _run() -> None:
    try:
        async with UnitOfWork(get_session_factory()) as uow:
            await rebuild_all_resource_state(uow.session)
    finally:
        await dispose_engine()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
