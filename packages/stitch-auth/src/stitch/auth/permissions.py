"""Shared Stitch permission constants and exact-match helpers."""

from __future__ import annotations

import logging
from collections.abc import Collection, Iterable
from typing import TypeAlias

logger = logging.getLogger(__name__)

Permission: TypeAlias = str

RESOURCE_READ: Permission = "resource:read"
RESOURCE_WRITE: Permission = "resource:write"

SOURCE_READ_PREFIX = "source:read:"
SOURCE_READ_RMI: Permission = f"{SOURCE_READ_PREFIX}rmi"
SOURCE_READ_GEM: Permission = f"{SOURCE_READ_PREFIX}gem"
SOURCE_READ_WM: Permission = f"{SOURCE_READ_PREFIX}wm"
SOURCE_READ_LLM: Permission = f"{SOURCE_READ_PREFIX}llm"
SOURCE_READ_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        SOURCE_READ_RMI,
        SOURCE_READ_GEM,
        SOURCE_READ_WM,
        SOURCE_READ_LLM,
    }
)
SOURCE_WRITE: Permission = "source:write"

MERGE_CANDIDATE_READ: Permission = "merge-candidate:read"
MERGE_CANDIDATE_CREATE: Permission = "merge-candidate:create"
MERGE_CANDIDATE_REVIEW: Permission = "merge-candidate:review"

SERVICE_ENTITY_LINKAGE_RUN: Permission = "service:entity-linkage:run"
SERVICE_LLM_SUGGEST: Permission = "service:llm:suggest"

ALL_PERMISSIONS: frozenset[Permission] = frozenset(
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


def source_read_permission(source: str) -> Permission:
    return f"{SOURCE_READ_PREFIX}{source}"


def source_from_read_permission(
    permission: str,
    *,
    valid_sources: Collection[str],
) -> str | None:
    if not permission.startswith(SOURCE_READ_PREFIX):
        return None

    source = permission[len(SOURCE_READ_PREFIX) :]
    if not source or ":" in source:
        return None
    if source not in valid_sources:
        logger.warning("ignoring unknown source in permission: %r", permission)
        return None
    return source


def source_read_sources(
    permissions: Iterable[str],
    *,
    valid_sources: Collection[str],
) -> frozenset[str]:
    sources = {
        source
        for permission in permissions
        if (
            source := source_from_read_permission(
                permission,
                valid_sources=valid_sources,
            )
        )
        is not None
    }
    return frozenset(sources)


def missing_permissions(
    granted: Collection[str],
    required: Iterable[str],
) -> frozenset[str]:
    return frozenset(permission for permission in required if permission not in granted)


def has_all_permissions(
    granted: Collection[str],
    required: Iterable[str],
) -> bool:
    return not missing_permissions(granted, required)


def has_any_permission(
    granted: Collection[str],
    candidates: Iterable[str],
) -> bool:
    return any(permission in granted for permission in candidates)
