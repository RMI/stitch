"""Shared Stitch permission constants and exact-match helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection, Iterable
from typing import Literal, NoReturn, TypeAlias

from .errors import InsufficientPermissionsError

logger = logging.getLogger(__name__)

Permission: TypeAlias = str

RESOURCE_READ: Permission = "resource:read"
RESOURCE_WRITE: Permission = "resource:write"

SOURCE_READ_PREFIX = "source:read:"
SOURCE_READ_RMI: Permission = f"{SOURCE_READ_PREFIX}rmi"
SOURCE_READ_GEM: Permission = f"{SOURCE_READ_PREFIX}gem"
SOURCE_READ_WM: Permission = f"{SOURCE_READ_PREFIX}wm"
SOURCE_READ_LLM: Permission = f"{SOURCE_READ_PREFIX}llm"
SOURCE_READ_CCR: Permission = f"{SOURCE_READ_PREFIX}ccr"
SOURCE_READ_BC: Permission = f"{SOURCE_READ_PREFIX}bc"
SOURCE_READ_ALB: Permission = f"{SOURCE_READ_PREFIX}alb"
SOURCE_READ_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        SOURCE_READ_RMI,
        SOURCE_READ_GEM,
        SOURCE_READ_WM,
        SOURCE_READ_LLM,
        SOURCE_READ_CCR,
        SOURCE_READ_BC,
        SOURCE_READ_ALB,
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


def check_permissions(
    granted: Iterable[str],
    required: Iterable[str],
    check: Literal["all", "any"] = "all",
    exc_handler: Callable[[InsufficientPermissionsError], NoReturn] | None = None,
) -> None:
    """Verify that granted permissions satisfy required permissions.

    Args:
        granted: Permissions granted to the caller.
        required: Permissions required for the protected operation.
        check: Whether all required permissions or any required permission must be
            granted.
        exc_handler: Optional callback for mapping permission failures to a
            caller-specific exception. This callback should raise an exception.

    Raises:
        ValueError: If check is not "all" or "any".
        InsufficientPermissionsError: If the required permissions are not
            satisfied and exc_handler does not raise its own exception.
    """
    if check not in {"all", "any"}:
        msg = f"unsupported permission check mode: {check!r}"
        raise ValueError(msg)

    granted_set = frozenset(granted)
    required_set = frozenset(required)
    if not required_set:
        return None

    if check == "all":
        missing = required_set.difference(granted_set)
        if not missing:
            return None
    else:
        missing = required_set.difference(granted_set)
        if missing != required_set:
            return None

    exc = InsufficientPermissionsError(
        granted=granted_set,
        required=required_set,
        missing=missing,
    )
    if exc_handler is not None:
        exc_handler(exc)
    raise exc
