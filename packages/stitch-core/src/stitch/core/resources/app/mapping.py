from stitch.core.resources.domain.entities import ResourceEntityData
from stitch.core.resources.domain.ports import SourceRecordData


def source_record_to_resource_data(
    record: SourceRecordData, dataset: str, source_pk: str
) -> ResourceEntityData:
    return ResourceEntityData(
        dataset=dataset,
        source_pk=source_pk,
        country_iso3=record["country_iso3"],
        name=record["name"],
        operator=record["operator"],
        latitude=record["latitude"],
        longitude=record["longitude"],
    )
