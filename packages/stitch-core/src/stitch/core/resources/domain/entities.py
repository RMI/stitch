from __future__ import annotations
from ast import TypeAlias
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Required, TypedDict

UserPlaceholder: TypeAlias = str


@dataclass(frozen=True, kw_only=True)
class AggregateResourceEntity:
    """A view-like object to capture a `ResourceEntity` that is aggregation of its constituent `ResourceEntity` objects.

    Note: `constituents` may themselves be aggregate resources.

    Attributes:
        root: the primary `ResourceEntity` for this object
        constituents: the `ResourceEntity` objects whose `repointed_to` attribute points to `root`
        source_data:
            source data aggregated through the `MembershipEntity` relationships
            ```
            source_data = {
              [source]: {
                [source_pk]: { ... [raw source data] ... }
              }
            }
            ```
    """

    root: ResourceEntity
    constituents: Sequence[ResourceEntity]
    source_data: Mapping[str, Mapping[str, SourceEntity]]


@dataclass(frozen=True, kw_only=True)
class ResourceEntity:
    """Minimal object to relate resources to one another.

    Attributes:
        id: unique identifier
        repointed_to: `id` field for the new parent/aggregate resource, None if not merged
        name: the resource name
        country: ISO 3166-1 country code
        latitude: the entity latitude
        longitude: the entity longitude
        last_updated: last update timestamp
        created: creation timestamp
        created_by: id for the user/service/process responsible for creating the resource
    """

    id: int
    repointed_to: int | None = None
    name: str
    country: str
    latitude: float | None = None
    longitude: float | None = None
    last_updated: datetime
    created: datetime
    created_by: UserPlaceholder | None = None

    def __eq__(self, other) -> bool:
        if not isinstance(other, ResourceEntity):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash((self.id, self.name, self.latitude, self.longitude))


class ResourceEntityData(TypedDict, total=False):
    name: Required[str]
    country: Required[str]
    repointed_to: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    created_by: UserPlaceholder | None = None


@dataclass(frozen=True, kw_only=True)
class MembershipEntity:
    """Primary connection between external/unknown data sources and resources.

    There's a 1-to-1 mapping between "source" + "source_pk" and resource_id.

    When merging resources together, we'll create new MembershipEntities that use the newly
    created `resource_id`.

    Splitting resources follows a similar pattern where new memberships are created that point
    constituent source data to the appropriate resource_ids.

    Attributes:
        id: identifier for the Membership
        resource_id: the Resource identifier
        source: table name or other identifier for the source collection
        source_pk: unique identifier for the row/entity within the specified `source`
        status: status of this Membership ("repointed", "deprecated", "invalid", etc...)
        created_by: id for the user/service/process responsible for creating the resource
        created: creation timestamp
        updated: timestamp for last update to the entitiy
    """

    id: int
    resource_id: int
    source: str
    source_pk: str
    status: str | None = None
    created_by: UserPlaceholder | None = None
    created: datetime
    updated: datetime

    def __eq__(self, other) -> bool:
        if not isinstance(other, MembershipEntity):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(
            (self.id, self.resource_id, self.source, self.source_pk, self.status)
        )


class MembershipEntityData(TypedDict, total=False):
    resource_id: Required[int]
    source: Required[str]
    source_pk: Required[str]
    created_by: str | None = None
    status: str | None = None


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
