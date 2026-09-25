"""Guard the global default source ordering against drift from SOURCE_PRIORITY.

The old ``og_field_source_priority`` lookup table is gone; the global default rank
of a source key now comes from ``db.source_priority`` (derived from the canonical
``SOURCE_PRIORITY`` constant). This asserts that derivation stays aligned with the
single source of truth.
"""

from __future__ import annotations

from stitch.api.db.source_priority import FALLBACK_RANK, source_priority_rank
from stitch.ogsi.model import SOURCE_PRIORITY


def test_source_priority_rank_matches_source_priority():
    assert [source_priority_rank(src) for src in SOURCE_PRIORITY] == list(
        range(len(SOURCE_PRIORITY))
    )


def test_unknown_source_ranks_last():
    assert source_priority_rank("not-a-source") == FALLBACK_RANK
    assert FALLBACK_RANK >= len(SOURCE_PRIORITY)
