from __future__ import annotations
from ast import TypeAlias
from dataclasses import dataclass
from datetime import datetime
from typing import Required, TypedDict

UserPlaceholder: TypeAlias = str


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
    dataset: Required[str]
    source_pk: Required[str]
    created_by: str | None = None
    status: str | None = None
