from typing import Any

from sqlalchemy.orm import Session
from .model.resource import ResourceModel
from stitch.core.resources.domain.entities import ResourceEntity
from stitch.core.resources.domain.ports import ResourceRepository


def normalize_resource_model(model: ResourceModel) -> dict[str, Any]:
    """Translate provider-specific ORM row into the normalized dict expected by domain."""
    projection = {
        "id": model.id,
        "dataset": model.dataset,
        "source_pk": model.source_pk,
        "repointed_id": model.repointed_id,
        "name": model.name,
        "country_iso3": model.country_iso3,
        "operator": model.operator,
        "latitude": float(model.latitude) if model.latitude is not None else None,
        "longitude": float(model.longitude) if model.longitude is not None else None,
        "created": model.created,
    }
    return projection


class SQLResourceRepository(ResourceRepository):
    _session: Session

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        dataset: str | None,
        source_pk: str | None,
        repointed_id: int | None = None,
        name: str | None = None,
        country_iso3: str | None = None,
        operator: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> int:
        model = ResourceModel(
            dataset=dataset,
            source_pk=source_pk,
            repointed_id=repointed_id,
            name=name,
            country_iso3=country_iso3,
            operator=operator,
            latitude=latitude,
            longitude=longitude,
        )
        self._session.add(model)
        self._session.flush()
        return model.id

    def get(self, resource_id: int) -> ResourceEntity | None:
        model = self._session.get(ResourceModel, resource_id)
        if model is None:
            return None
        return self._model_to_entity(model)

    def get_root_resource(self, resource_id: int):
        """Trace the `repointed_id` values until reaching a `ResourceModel` where  repointed_id is None/null"""
        pass

    def repoint_resource(self, resource_id: int, to_resource_id: int):
        """
        Update the resource's `repointed_id`  to `to_resource_id`
        """

    def _model_to_entity(self, model: ResourceModel):
        return ResourceEntity(**normalize_resource_model(model))
