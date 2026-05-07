"""Auth0 permission claim parsing.

All knowledge of permission-string grammar lives here. Callers receive a
typed `frozenset[OGSISrcKey]`; new permission shapes are added as new
free functions in this module without touching the rest of the API.
"""

import logging
from typing import cast, get_args

from stitch.auth import TokenClaims
from stitch.ogsi.model.types import OGSISrcKey

logger = logging.getLogger(__name__)

_LICENSED_PREFIX = "resource:read:licensed:"
_VALID_SOURCES: frozenset[str] = frozenset(get_args(OGSISrcKey))


def licensed_sources(claims: TokenClaims) -> frozenset[OGSISrcKey]:
    """Return the set of OGSI sources the caller is licensed to read."""
    out: set[OGSISrcKey] = set()
    for perm in claims.permissions:
        if not perm.startswith(_LICENSED_PREFIX):
            continue
        candidate = perm[len(_LICENSED_PREFIX) :]
        if candidate in _VALID_SOURCES:
            out.add(cast(OGSISrcKey, candidate))
        else:
            logger.debug("ignoring unknown source in permission: %r", perm)
    return frozenset(out)
