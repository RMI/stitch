from abc import ABC
from collections import defaultdict
from collections.abc import Sequence
from typing import Any, Mapping


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

    # TODO: consider a decorator to wrap methods in a TransactionContext
    def create_resource(self, source: str, data: Mapping[str, Any]):
        with self.tx:
            src_repo = self.tx.source_registry.get_source_repository(source)
            rec_data = src_repo.row_to_record_data(data)
            source_pk = src_repo.write(rec_data)
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
        *resources: Sequence[ResourceEntity | int],
    ) -> AggregateResourceEntity:
        with self.tx:
            new_resource = self.tx.resources.merge_resources(*resources)
            new_mems = self.tx.memberships.create_repointed_memberships(
                from_resources=resources, to_resource=new_resource
            )
            # get source data from memberships
            data: dict[str, dict[str, SourceEntity]] = defaultdict(dict)
            # TODO: consider new method on SourceRepository:
            # - `get_aggregate_data(ids: Sequence[tuple["source", "source_pk"]]) -> dict[str, dict[str, SourceEntity]]`
            for member in new_mems:
                repo = self.tx.source_registry.get_source_repository(member.source)
                entity = repo.fetch(source_pk=member.source_pk)
                data[member.source][member.source_pk] = entity

            return AggregateResourceEntity(
                root=new_resource, constituents=resources, source_data=data
            )
