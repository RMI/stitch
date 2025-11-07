"""
The `resources.domain.ports` package defines the primary external interfaces
that a given caller must implement in order for the underlying memberships and
aggregations to function properly.

Declaring them here (within our `domain` package) ensures that concrete/implmentation details
depend upon core abstractions instead of the other way around. This offers a lot of freedom to
change the details of persistence (db engine, schemas, operations), presentation (API, UI, CLI), or
external services (e.g. "entity recognition/matching") without the need to make any commensurate
changes here.
"""

from .context import TransactionContext
from .repositories import (
    ResourceRepository,
    MembershipRepository,
)
from .sources import (
    SourcePersistenceRepository,
    SourceRecord,
    SourceRegistry,
    SourceRegistryFactory,
    SourceRecordData,
)

__all__ = [
    "ResourceRepository",
    "TransactionContext",
    "SourcePersistenceRepository",
    "SourceRecord",
    "SourceRegistry",
    "SourceRegistryFactory",
    "MembershipRepository",
    "SourceRecordData",
]
