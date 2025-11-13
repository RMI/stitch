from collections.abc import Sequence, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import (
    Any,
    Protocol,
    Required,
    TypedDict,
    Unpack,
)

from sqlalchemy.orm import Session

from stitch.core.resources.domain.entities import SourceEntity, SourceRecord


# TODO: consider making this Generic where the type, `T`, corresponds to the
# entity type, e.g. `GemEntity` or `WoodmacFieldEntity`
class SourceRepository(Protocol):
    """Abstract interface for interacting with unknown source data stores.

    Domain-specific implementations can handle their own storage mechanisms and schemas
    so long as they abide by this contract. This allows the `resources` package to
    coordinate storage operations without any specific knowledge of the underlying details.
    """

    @property
    def source_name(self) -> str:
        """Unique collection/table identifier."""

    def write(
        self,
        entity_data: SourceRecord | None = None,
        /,
        **kwargs: Unpack[SourceRecord],
    ) -> str:
        """Persist record and return new id"""

    def fetch(self, source_pk: str) -> SourceEntity | None:
        """Retrieve entity record by id. Return `None` if it doesn't exist."""
        pass

    def fecth_many(self, source_pks: list[str]) -> Sequence[SourceEntity]:
        """Retrieve multiple source entities"""

    def row_to_record_data(self, data: Mapping[str, Any]) -> SourceRecord:
        """Translate source data to record data structure."""


class SourceRegistry(Protocol):
    """Interface for getting and checking references to external `SourceRepository` implementations."""

    def is_source(self, name: str) -> bool:
        """Check if a name exists as a source in the registry."""

    def get_source_repository(self, source: str) -> SourceRepository:
        """Fetch a `SourceRepository` for the specified identifier."""


class SourceRegistryFactory(Protocol):
    """Generic representation of any callable that returns a valid `SourceRegistry` instance."""

    def __call__(self, session: Session) -> SourceRegistry:
        pass
