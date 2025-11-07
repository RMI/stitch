from typing import Protocol
from collections.abc import Sequence

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
        name: str,
        country: str,
        repointed_id: int | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        created_by: UserPlaceholder | None = None,
    ) -> int:
        """Create new Resource and return unique resource identifier"""

    def get_by_id(self, resource_id: int) -> ResourceEntity | None:
        """Retrieve resource by identifier

        Args:
            resource_id: the resource identifier

        Returns:
            The associated Resource

        Raises:
            EntityNotFoundError if no Resource with `resource_id` is found

        """

    def find_root_resource_by_id(self, resource_id: int) -> ResourceEntity:
        """Follow the id repointing until we find an "unrepointed" resource"""

    def split_resources_by_id(
        self, subject_id: int, from_id: int
    ) -> tuple[ResourceEntity, ResourceEntity]:
        """Remove the relationship between the `subject` resource  from its current aggregate.

        Returns the pair of new resources: ("removed" resource, "from" resource)

        """

    def get_all_connected_resources(
        self, id: int | ResourceEntity
    ) -> Sequence[ResourceEntity]:
        """Find all resource ids that either point to or are pointed to by `id`"""


class MembershipRepository(Protocol):
    """
    Interface for data storage operations around Memberships.
    """

    def get(self, membership_id: int) -> MembershipEntity:
        """Retrieve membership by id.

        Args:
            membership_id: unique identifier for the membership

        Returns:
            The associated Membership

        Raises:
            EntityNotFoundError if no Membership is found
        """
        pass

    def create(
        self,
        resource_id: int,
        dataset: str,
        source_pk: str,
        status: str | None = None,
        created_by: UserPlaceholder | None = None,
    ) -> ResourceEntity:
        pass

    def repoint_memberships(ids: Sequence[int], to_resource_id: int):
        """Updates all memberships to point to the provided id."""
