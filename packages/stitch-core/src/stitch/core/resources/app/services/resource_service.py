from abc import ABC
from collections import defaultdict
from typing import Any, Mapping


from stitch.core.resources.adapters.sql.errors import (
    ResourceIntegrityError,
)
from stitch.core.resources.app.mapping import source_record_to_resource_data
from stitch.core.resources.domain.entities import (
    AggregateResourceEntity,
    ResourceEntity,
    SourceEntity,
)
from stitch.core.resources.domain.ports import (
    TransactionContext,
)


class AbstractService(ABC):
    tx: TransactionContext

    def __init__(self, tx_ctx: TransactionContext) -> None:
        self.tx = tx_ctx


class ResourceService(AbstractService):
    def __init__(
        self,
        tx_ctx: TransactionContext,
    ):
        super().__init__(tx_ctx=tx_ctx)

    def get_aggregate_resource(self, id: int) -> AggregateResourceEntity:
        with self.tx:
            root = self.tx.resources.get(resource_id=id)
            if root.repointed_to is not None:
                msg = f"Attempt to aggregate repointed resource: {root}"
                raise ResourceIntegrityError(msg)
            return AggregateResourceEntity(
                root=root,
                constituents=self.tx.resources.get_constituents(resource=root),
                source_data=self._aggregate_resource_data(resource_id=root.id),
            )

    def get_all_resources(self):
        """Fetch all root resources as a `Generator`.

        Yields:
            The AggregateResourceEntity for each resource
        """
        with self.tx:
            for res in self.tx.resources.get_all_root_resources():
                constituents = self.tx.resources.get_constituents(res)
                data = self._aggregate_resource_data(resource_id=res.id)
                yield AggregateResourceEntity(
                    root=res, constituents=constituents, source_data=data
                )

    def get_resource(self, resource_id: int) -> ResourceEntity:
        """Fetch the resource with the given id.

        Args:
            resource_id: resource id

        Returns:
            The found resource entity.

        Raises:
            EntityNotFoundError
        """
        with self.tx:
            return self.tx.resources.get(resource_id=resource_id)

    def get_root_resource(self, resource_id: int) -> AggregateResourceEntity:
        """Fetch the root/parent aggregate resource for a given resource id

        If the resource_id is already a root, we return it with its aggregate data.
        If the resource_id hasn't been repointed, return it as an aggregate with empty constituent
        and source data.

        Args:
            resource_id: the

        Returns:
            The final `AggregateResourceEntity`
        """
        with self.tx:
            resource = self.tx.resources.get_root_resource(resource_id)
            return AggregateResourceEntity(
                root=resource,
                constituents=self.tx.resources.get_constituents(resource),
                source_data=self._aggregate_resource_data(resource.id),
            )

    def create_resource(self, source: str, data: Mapping[str, Any]):
        with self.tx:
            src_repo = self.tx.source_registry.get_source_repository(source)
            rec_data = src_repo.row_to_record_data(data)
            source_pk = src_repo.write(**rec_data)
            resource_kwargs = source_record_to_resource_data(
                source=source, record=rec_data, source_pk=source_pk
            )
            resource_id = self.tx.resources.create(**resource_kwargs)
            _member_id = self.tx.memberships.create(
                resource_id=resource_id, source=source, source_pk=source_pk
            )
            return self.tx.resources.get(resource_id=resource_id)

    def merge_resources(
        self,
        *resources: ResourceEntity | int,
    ) -> AggregateResourceEntity:
        with self.tx:
            new_resource, constituents = self.tx.resources.merge_resources(*resources)
            new_mems = self.tx.memberships.create_repointed_memberships(
                from_resources=resources, to_resource=new_resource
            )
            # get source data from memberships
            data: dict[str, dict[str, SourceEntity]] = defaultdict(dict)
            for member in new_mems:
                repo = self.tx.source_registry.get_source_repository(member.source)
                entity = repo.fetch(source_pk=member.source_pk)
                if entity is None:
                    continue
                data[member.source][member.source_pk] = entity

            return AggregateResourceEntity(
                root=new_resource, constituents=constituents, source_data=data
            )

    def _aggregate_resource_data(self, resource_id: int):
        refs = self.tx.memberships.get_source_refs(resource_id=resource_id)
        data: dict[str, dict[str, SourceEntity]] = {}
        for source, source_pks in refs.items():
            src_repo = self.tx.source_registry.get_source_repository(source)
            data[source] = {
                str(src_ent.id): src_ent for src_ent in src_repo.fetch_many(source_pks)
            }
        return data
