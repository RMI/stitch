from __future__ import annotations

from typing import Protocol


from stitch.core.resources.domain.ports.repositories import (
    MembershipRepository,
    ResourceRepository,
)
from stitch.core.resources.domain.ports.sources import (
    DatasetRegistry,
)


class TransactionContext(Protocol):
    """ContextManager interface to represent the idea of a "unit of work" or SQL transaction.

    Allows for ACID compliance for multiple data operations.

    Attributes:
        resources: Resource data/persistence operations interface
        memberships: Membership data/persistence operations interface
        source_registry: primary interface for interacting with unspecified/unknown dataset storage mechanisms
    """

    resources: ResourceRepository
    memberships: MembershipRepository
    source_registry: DatasetRegistry

    def __enter__(self) -> TransactionContext:
        """Begin transaction"""

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Commit or rollback based on exception status"""

    def commit(self) -> None:
        """Explicitly commit transaction"""

    def rollback(self) -> None:
        """Explicitly rollback transaction"""
