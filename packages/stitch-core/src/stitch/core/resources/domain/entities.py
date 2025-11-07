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
        resource_id: unique identifier
        name: the resource name
        country: ISO 3166-1 country code
        repointed_id: `id` field for the new parent/aggregate resource, None if not merged
        created: creation timestamp
        updated: last update timestamp
        created_by: id for the user/service/process responsible for creating the resource
    """

    resource_id: int
    name: str
    country: str
    latitude: float | None = None
    longitude: float | None = None
    repointed_id: int | None = None
    created: datetime
    created_by: UserPlaceholder | None = None
    last_updated: datetime

    def __eq__(self, other) -> bool:
        if not isinstance(other, ResourceEntity):
            return False
        return self.resource_id == other.resource_id

    def __hash__(self) -> int:
        return hash((self.resource_id, self.dataset, self.source_pk))


@dataclass(frozen=True, kw_only=True)
class MembershipEntity:
    """Primary connection between external/unknown data sources and resources.

    There's a 1-to-1 mapping between "dataset" + "source_pk" and resource_id.

    When merging resources together, we'll create new MembershipEntities that use the newly
    created `resource_id`.

    Splitting resources follows a similar pattern where new memberships are created that point
    constituent source data to the appropriate resource_ids.

    Attributes:
        id: identifier for the Membership
        resource_id: the Resource identifier
        dataset: table name or other identifier for the source collection
        source_pk: unique identifier for the row/entity within the specified `dataset`
        status: status of this Membership ("repointed", "deprecated", "invalid", etc...)
        created_by: id for the user/service/process responsible for creating the resource
        created: creation timestamp
        updated: timestamp for last update to the entitiy
    """

    id: int
    resource_id: int
    dataset: str
    source_pk: str
    status: str | None = None
    created_by: UserPlaceholder | None = None
    created: datetime
    updated: datetime
