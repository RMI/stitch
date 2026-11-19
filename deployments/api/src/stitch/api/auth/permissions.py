from typing import cast, get_args

from stitch.ogsi.model.types import OGSISrcKey

from .typings import TokenClaims

RESOURCE_READ = "resource:read"
RESOURCE_WRITE = "resource:write"

SOURCE_READ_PREFIX = "source:read:"
SOURCE_READ_ANY = f"{SOURCE_READ_PREFIX}*"
SOURCE_WRITE = "source:write"

MERGE_CANDIDATE_READ = "merge-candidate:read"
MERGE_CANDIDATE_CREATE = "merge-candidate:create"
MERGE_CANDIDATE_REVIEW = "merge-candidate:review"

SERVICE_ENTITY_LINKAGE_RUN = "service:entity-linkage:run"
SERVICE_LLM_SUGGEST = "service:llm:suggest"

_VALID_SOURCES: frozenset[str] = frozenset(get_args(OGSISrcKey))

SOURCE_READ_PERMISSIONS: frozenset[str] = frozenset(
    f"{SOURCE_READ_PREFIX}{source}" for source in _VALID_SOURCES
)

ALL_PERMISSIONS: frozenset[str] = frozenset(
    {
        RESOURCE_READ,
        RESOURCE_WRITE,
        *SOURCE_READ_PERMISSIONS,
        SOURCE_WRITE,
        MERGE_CANDIDATE_READ,
        MERGE_CANDIDATE_CREATE,
        MERGE_CANDIDATE_REVIEW,
        SERVICE_ENTITY_LINKAGE_RUN,
        SERVICE_LLM_SUGGEST,
    }
)


def licensed_sources(claims: TokenClaims) -> frozenset[OGSISrcKey]:
    return frozenset(
        cast(OGSISrcKey, permission.removeprefix(SOURCE_READ_PREFIX))
        for permission in claims.permissions
        if permission in SOURCE_READ_PERMISSIONS
    )
