from typing import Protocol
from collections.abc import Iterable, Mapping, Sequence

from stitch.core.resources.domain.entities import (
    ResourceEntity,
    UserPlaceholder,
)
from stitch.core.resources.domain.entities import MembershipEntity


class ResourceRepository(Protocol):
    """
    Internal interface declaring the needed operations and contract for interacting with Resource
    data storage/persistence.
    """

    def create(
        self,
        name: str | None = None,
        country: str | None = None,
        repointed_to: int | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        created_by: UserPlaceholder | None = None,
    ) -> int:
        """Create new Resource and return unique resource identifier"""
        ...

    def get(self, resource_id: int) -> ResourceEntity:
        """Retrieve resource by identifier

        Args:
            resource_id: the resource identifier

        Returns:
            The associated Resource

        Raises:
            EntityNotFoundError if no Resource with `resource_id` is found
        """
        ...

    def get_multiple(self, *ids: int) -> Sequence[ResourceEntity]:
        """Fetch multiple resources by id"""
        ...

    def get_all_root_resources(self) -> Iterable[ResourceEntity]:
        """Get all root resources"""
        ...

    def get_constituents(
        self, resource: ResourceEntity | int
    ) -> Sequence[ResourceEntity]:
        """Get all resources that have been repointed to `resource`"""
        ...

    def merge_resources(
        self, *resources: ResourceEntity | int
    ) -> tuple[ResourceEntity, Sequence[ResourceEntity]]:
        """Merge 2 or more resources to create a new parent.

        Args:
            *resources: sequence of positional resource entities or ids

        Returns:
            A 2-tuple of (new parent resource, constituents)
        """
        ...

    def split_resource(self, resource_id: int) -> ResourceEntity:
        """Remove the resource id from its parent aggregate"""
        ...


class MembershipRepository(Protocol):
    """
    Interface for data storage operations around Memberships.
    """

    def get(self, membership_id: int) -> MembershipEntity | None:
        """Retrieve membership by id.

        Args:
            membership_id: unique identifier for the membership

        Returns:
            The associated Membership, or None if not found
        """
        pass

    def get_active_members(self, resource_id: int) -> Sequence[MembershipEntity]:
        """Retrieve all membership entities connected to the `resource_id`.

        Args:
            resource_id: the target resource id

        Returns:
            A list of memberships
        """
        ...

    def get_source_refs(self, resource_id: int) -> Mapping[str, Sequence[str]]:
        """Fetch a mapping of all sources and primary keys related to the `resource_id`.

        Structure:
        ```
        {
            [source]: [... source primary keys ...]
        }
        ```
        """
        ...

    def create(
        self,
        resource_id: int,
        source: str,
        source_pk: str,
        status: str | None = None,
        created_by: UserPlaceholder | None = None,
    ) -> int: ...

    def create_repointed_memberships(
        self,
        from_resources: Sequence[ResourceEntity | int],
        to_resource: ResourceEntity | int,
    ) -> Sequence[MembershipEntity]:
        """Updates all memberships to point to the provided id."""
        ...
