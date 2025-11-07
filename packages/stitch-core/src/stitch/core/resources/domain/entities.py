from __future__ import annotations
from ast import TypeAlias
from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict

UserPlaceholder: TypeAlias = str


@dataclass(frozen=True, kw_only=True)
class ResourceEntity:
    """Minimal object to relate resources to one another.

    Attributes:
        id: unique identifier
        repointed_id: `id` field for the new parent/aggregate resource, None if not merged
        created: creation timestamp
        updated: last update timestamp
        created_by: id for the user/service/process responsible for creating the resource
    """

    resource_id: int
    name: str
    country: str
    latitude: float
    longitude: float
    repointed_id: int | None = None
    created: datetime
    created_by: UserPlaceholder | None = None

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
        id:
        resource_id:
        dataset:
        source_pk:
        created_by:
        status:
        created:
    """

    id: int
    resource_id: int
    dataset: str
    source_pk: str
    created_by: UserPlaceholder | None = None
    status: str | None = None
    created: datetime
