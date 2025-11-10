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
class SourceEntity:
    """Generic representation of a row/entity from a raw/external data source.

    Establishes a minimal structure (aligned with our `Resource` definition) that a
    `SourceRepositry` implementation can fulfill.

    Attributes:
        id: the unique record identifier within the source collection/table
        source: the collection/table identifier (e.g. "gem", "woodmac", or other domain-specific string)
        name: the entity/record name
        country: ISO 3166-1 country code
        latitude: optional latitude
        longitude: optional longitude
        payload: the underlying source data with an unspecified structure/schema
        created: creation timestamp
    """

    id: int
    source: str
    name: str
    country: str
    latitude: float | None
    longitude: float | None
    payload: object | Mapping[str, Any]
    created: datetime


class SourceRecord(TypedDict, total=False):
    """Convenience class for passing around `SourceEntity` data."""

    source: Required[str]
    name: Required[str]
    payload: Required[object | Mapping[str, Any]]
    country: Required[str]
    latitude: float | None
    longitude: float | None


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
