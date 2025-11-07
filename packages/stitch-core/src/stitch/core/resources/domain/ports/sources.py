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


@dataclass(frozen=True)
class SourceRecord:
    """Generic representation of a row/entity from a raw/external data source.

    Establishes a minimal structure (aligned with our `Resource` definition) that a
    `SourceRepositry` implementation can fulfill.

    Attributes:
        id: the unique record identifier within the source collection/table
        dataset: the collection/table identifier (e.g. "gem", "woodmac", or other domain-specific string)
        name: the entity/record name
        country: ISO 3166-1 country code
        latitude: optional latitude
        longitude: optional longitude
        payload: the underlying source data with an unspecified structure/schema
        created: creation timestamp
    """

    id: int
    dataset: str
    name: str
    country: str
    latitude: float | None
    longitude: float | None
    payload: object | Mapping[str, Any]
    created: datetime


class SourceRecordData(TypedDict, total=False):
    """Convenience class for passing around `SourceRecord` data."""

    dataset: Required[str]
    name: Required[str]
    payload: Required[object | Mapping[str, Any]]
    country: Required[str]
    latitude: float | None
    longitude: float | None


class SourcePersistenceRepository(Protocol):
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
        entity_data: SourceRecordData | None = None,
        /,
        **kwargs: Unpack[SourceRecordData],
    ) -> str:
        """Persist record and return new id"""

    def fetch(self, source_id: str) -> SourceRecord | None:
        """Retrieve entity record by id. Return `None` if it doesn't exist."""
        pass

    def fecth_many(self, source_ids: list[str]) -> Sequence[SourceRecord]:
        """Retrieve multiple source entities"""

    def row_to_record_data(self, data: Mapping[str, Any]) -> SourceRecordData:
        """Translate source data to record data structure."""


class SourceRegistry(Protocol):
    """Interface for getting and checking references to external `Source` data storage features."""

    def is_source(self, name: str) -> bool:
        """Check if a name exist as a source."""

    def get_source_repository(self, source_name: str) -> SourcePersistenceRepository:
        """Fetch a source data access repository"""


class SourceRegistryFactory(Protocol):
    """Generic representation of any callable that returns a valid `SourceRegistry` instance."""

    def __call__(self, session: Session) -> SourceRegistry:
        pass
