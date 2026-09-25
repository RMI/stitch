"""Global default source ordering, derived from the canonical ``SOURCE_PRIORITY``.

With the per-attribute priority table (``og_field_resource_attribute_priority``)
replacing the old ``og_field_source_priority`` lookup table, the *global* default
rank of a source key now comes straight from the ``SOURCE_PRIORITY`` constant
rather than a DB row. This module is the single place that maps a source key to
its rank, for both SQL (``source_priority_case``) and Python (``source_priority_rank``).

Lower rank wins, matching the coalescing convention.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import Case, ColumnElement, case
from stitch.ogsi.model import SOURCE_PRIORITY

_RANK: Final[dict[str, int]] = {src: rank for rank, src in enumerate(SOURCE_PRIORITY)}

# Rank assigned to an unknown source key: after every known source.
FALLBACK_RANK: Final[int] = len(SOURCE_PRIORITY)


def source_priority_rank(source: str) -> int:
    """The global default rank of a source key (lower wins)."""
    return _RANK.get(source, FALLBACK_RANK)


def source_priority_case(source_col: ColumnElement[str]) -> Case[int]:
    """SQL expression mapping a ``source`` column to its global default rank."""
    return case(_RANK, value=source_col, else_=FALLBACK_RANK)
