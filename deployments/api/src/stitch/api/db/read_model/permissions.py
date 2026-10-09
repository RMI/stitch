"""The exact permission profiles the resource-state read model stores.

The read model keeps one coalesced row per resource for each of four profiles,
identified by ``permission_mask``:

    0 = PUBLIC
    1 = PUBLIC + ccr
    2 = PUBLIC + wm
    3 = PUBLIC + wm + ccr

A caller is served from the read model only when their licensed sources *exactly
equal* one of these sets. Anything else -- a partial public grant, an extra or
unknown key, or an unscoped (``None``) caller -- uses live coalescing. There is no
subset or closest-profile matching, so a cached answer can never show a caller more
(or less) than live coalescing would.

The sets are spelled out literally rather than derived from ``OGSISrcKey``: a new
source key must be added here deliberately. Until then every caller holding it
falls back to live (fail closed), and a drift test flags the gap.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Final

from stitch.ogsi.model.types import OGSISrcKey

PUBLIC_SOURCES: Final[frozenset[OGSISrcKey]] = frozenset(
    {"gem", "rmi", "llm", "alb", "bc", "nor"}
)
RESTRICTED_SOURCES: Final[frozenset[OGSISrcKey]] = frozenset({"wm", "ccr"})

PROFILES: Final[dict[int, frozenset[OGSISrcKey]]] = {
    0: PUBLIC_SOURCES,
    1: PUBLIC_SOURCES | {"ccr"},
    2: PUBLIC_SOURCES | {"wm"},
    3: PUBLIC_SOURCES | {"wm", "ccr"},
}

PERMISSION_MASKS: Final[tuple[int, ...]] = tuple(PROFILES)

_MASK_BY_PROFILE: Final[dict[frozenset[OGSISrcKey], int]] = {
    sources: mask for mask, sources in PROFILES.items()
}


def read_model_mask(sources: Collection[OGSISrcKey] | None) -> int | None:
    """The mask whose profile exactly equals ``sources``, else ``None`` (use live)."""
    if sources is None:
        return None
    return _MASK_BY_PROFILE.get(frozenset(sources))


def visible_sources_for_mask(mask: int) -> frozenset[OGSISrcKey]:
    """The exact source set a mask's rows are coalesced over."""
    return PROFILES[mask]
