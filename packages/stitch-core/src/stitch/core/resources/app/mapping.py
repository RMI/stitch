from collections.abc import Mapping
from stitch.core.resources.domain.entities import ResourceEntityData, SourceRecord


def source_record_to_resource_data(
    record: SourceRecord, source: str, source_pk: str
) -> ResourceEntityData:
    return ResourceEntityData(
        country=record.get("country", None),
        name=record.get("name", None),
        latitude=record.get("latitude", None),
        longitude=record.get("longitude", None),
    )
