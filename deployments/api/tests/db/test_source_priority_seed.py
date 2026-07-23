"""Guard against drift between the seeded priority table and SOURCE_PRIORITY.

The integration test DB seeds ``og_field_source_priority`` via
``metadata.create_all`` -> ``after_create`` -> ``DEFAULT_PRIORITIES`` (derived
from the canonical ``SOURCE_PRIORITY``). Asserting the seeded rows equal the
constant keeps the seed path aligned with the single source of truth.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stitch.api.db.model import OGFieldSourcePriority
from stitch.ogsi.model import SOURCE_PRIORITY


@pytest.mark.anyio
async def test_seeded_priorities_match_source_priority(
    integration_session: AsyncSession,
):
    result = await integration_session.execute(
        select(OGFieldSourcePriority).order_by(OGFieldSourcePriority.priority)
    )
    rows = result.scalars().all()

    assert [(row.source, row.priority) for row in rows] == [
        (source, i + 1) for i, source in enumerate(SOURCE_PRIORITY)
    ]
