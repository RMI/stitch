"""Permission-mask encoding for the current-state read model (STIT-766).

The precomputed read model stores one coalesced variant of each resource per
*visibility profile*. Only two source keys vary between users -- ``wm`` and
``ccr`` -- while every other source is a shared **public** tier that all users are
expected to hold read on (see the STIT-766 design). A resource therefore has at
most four variants, indexed by a two-bit ``permission_mask``:

    bit 1 (``CCR_BIT``) -> ``ccr`` visible
    bit 2 (``WM_BIT``)  -> ``wm`` visible

    0 = public only · 1 = public+ccr · 2 = public+wm · 3 = public+wm+ccr

A caller may only be served from the read model when their licensed set is one of
these four canonical profiles -- i.e. they hold read on *every* public source and
any combination of ``wm``/``ccr``. Anything else (a partial public grant) falls
back to live coalescing, so correctness never depends on the assumption holding.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Final, get_args

from stitch.ogsi.model import CCR_SRC, WM_SRC
from stitch.ogsi.model.types import OGSISrcKey

ALL_SOURCES: Final[frozenset[OGSISrcKey]] = frozenset(get_args(OGSISrcKey))

# The only source keys whose visibility varies between users.
RESTRICTED_SOURCES: Final[frozenset[OGSISrcKey]] = frozenset({WM_SRC, CCR_SRC})

# Sources every user is expected to be able to read (the "public" tier).
PUBLIC_SOURCES: Final[frozenset[OGSISrcKey]] = ALL_SOURCES - RESTRICTED_SOURCES

CCR_BIT: Final[int] = 1
WM_BIT: Final[int] = 2

# Every permission_mask a resource may be materialized for.
ALL_MASKS: Final[tuple[int, ...]] = (0, 1, 2, 3)


def mask_for_sources(sources: Collection[OGSISrcKey]) -> int:
    """The ``permission_mask`` for a visibility profile (only wm/ccr count)."""
    mask = 0
    if WM_SRC in sources:
        mask |= WM_BIT
    if CCR_SRC in sources:
        mask |= CCR_BIT
    return mask


def visible_sources_for_mask(mask: int) -> frozenset[OGSISrcKey]:
    """The source keys visible at ``mask``: the public tier plus wm/ccr per bit."""
    visible = set(PUBLIC_SOURCES)
    if mask & WM_BIT:
        visible.add(WM_SRC)
    if mask & CCR_BIT:
        visible.add(CCR_SRC)
    return frozenset(visible)


def is_canonical_profile(sources: Collection[OGSISrcKey]) -> bool:
    """True when ``sources`` is one of the four read-model visibility profiles.

    Requires read on every public source; ``wm``/``ccr`` may be present or not.
    A caller whose grants do not satisfy this must use live coalescing.
    """
    return PUBLIC_SOURCES <= frozenset(sources)


def read_model_mask(sources: Collection[OGSISrcKey] | None) -> int | None:
    """The mask to read for ``sources``, or ``None`` to fall back to live coalescing.

    ``None`` sources means "unscoped" (no licensing filter, e.g. internal calls);
    that intentionally uses the live path rather than the cache. A non-canonical
    grant (partial public tier) also returns ``None``.
    """
    if sources is None:
        return None
    if not is_canonical_profile(sources):
        return None
    return mask_for_sources(sources)
