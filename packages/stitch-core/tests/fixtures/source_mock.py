from typing import Any, Unpack
from stitch.core.resources.domain.ports import (
    SourcePersistenceRepository,
    SourceRecord,
    SourceRecordData,
)


class _Base(SourcePersistenceRepository):
    _data: list[SourceRecord]

    def __init__(self) -> None:
        self._data = []

    # def row_to_record_data(self, data: Mapping[str, Any]) -> SourceRecordData:
    #     return super().row_to_record_data(data)

    def write(
        self,
        entity_data: SourceRecordData | None = None,
        /,
        **kwargs: Unpack[SourceRecordData],
    ) -> str:
        to_write: SourceRecordData = (entity_data or {}) | kwargs
        id = max([row.id for row in self._data] + [0])
        record: SourceRecord = SourceRecord(id=id + 1, **to_write)
        self._data.append(record)
        return str(record.id)
