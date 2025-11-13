from abc import ABC
from typing import Any, Mapping


from stitch.core.resources.app.mapping import source_record_to_resource_data
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
    def create_resource(
        self, source: str, data: Mapping[str, Any], resource_id: int | None = None
    ):
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
            return resource_id
