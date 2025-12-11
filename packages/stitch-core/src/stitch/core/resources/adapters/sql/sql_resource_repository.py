from collections.abc import Generator, Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session

from stitch.core.resources.adapters.sql.common import extract_id
from stitch.core.resources.adapters.sql.errors import (
    EntityNotFoundError,
    ResourceIntegrityError,
)
from .model.resource import ResourceModel
from stitch.core.resources.domain.entities import (
    ResourceEntity,
    UserPlaceholder,
)
from stitch.core.resources.domain.ports import ResourceRepository


class SQLResourceRepository(ResourceRepository):
    _session: Session

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        name: str | None = None,
        country: str | None = None,
        repointed_to: int | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        created_by: UserPlaceholder | None = None,
    ) -> int:
        model = ResourceModel.create(
            repointed_to=repointed_to,
            name=name,
            country=country,
            latitude=latitude,
            longitude=longitude,
        )
        self._session.add(model)
        self._session.flush()
        return model.id

    def get(self, resource_id: int) -> ResourceEntity:
        model = self._session.get(ResourceModel, resource_id)
        if model is None:
            raise EntityNotFoundError(f"No resource with id {resource_id} found.")
        return model.as_entity()

    def get_multiple(self, *ids: int) -> Sequence[ResourceEntity]:
        return tuple(
            model.as_entity()
            for model in self._session.scalars(
                select(ResourceModel).where(ResourceModel.id.in_(ids))
            ).all()
        )

    def get_all_root_resources(self) -> Generator[ResourceEntity, None, None]:
        stmt = select(ResourceModel).where(ResourceModel.repointed_to.is_(None))
        return (m.as_entity() for m in self._session.scalars(stmt).all())

    def get_constituents(
        self, resource: ResourceEntity | int
    ) -> Sequence[ResourceEntity]:
        res_id = extract_id(resource)
        res_model = self._session.get(ResourceModel, res_id)
        if res_model is None:
            raise EntityNotFoundError()
        elif res_model.repointed_to is not None:
            raise
        # resource exists and has not been repointed
        # fetch all resources where `repointed_to == res_id`
        return tuple(
            r.as_entity()
            for r in self._session.scalars(
                select(ResourceModel).where(ResourceModel.repointed_to == res_id)
            )
        )

    def merge_resources(self, *resources: ResourceEntity | int):
        """Merge two or more resources and repoint them to the newly created resource.

        Merging constraints:
        * the ids/entities are not the same
        * all resources exist in the db
        * none has been repointed already

        Args:
            resources: a collection of unmerged resources

        Returns:
            The new resource pointed to by the passed entities.

        Raises:
            ResourceIntegrityError: If ids are the same or if either has been repointed
            EntityNotFoundError: If either `Resource` hasn't been persisted
        """
        ids = map(extract_id, resources)
        idset = set(ids)
        if len(idset) == 1:
            # we can't merge a single id
            raise ResourceIntegrityError(
                f"Merges are only possible between different resources. Found only id: {list(idset)[0]}"
            )
        stmt = select(ResourceModel).where(ResourceModel.id.in_(idset))
        models: Sequence[ResourceModel] = self._session.scalars(stmt).all()
        if len(models) < 2:
            # only 0 or 1 resource actually found in the db
            found_ids = [m.id for m in models]
            missing = [id_ for id_ in idset if id_ not in (m.id for m in models)]
            msg = (
                "Multiple Resources required for merging. "
                + f"Found ({','.join(map(str, found_ids))}). Missing ({','.join(map(str, missing))})"
            )
            raise ResourceIntegrityError(msg)

        if any([m.repointed_to is not None for m in models]):
            reprs = [repr(m) for m in models if m.repointed_to is not None]
            msg = f"Repointed: [{','.join(reprs)}]"
            raise ResourceIntegrityError(
                f"Cannot merge any resource that has already been merged. {msg}"
            )

        # once here, we know all Resources exist and none has been repointed
        # NOTE: We create an essentially empty resource. Determining which source data are used
        # to create the final aggregate resource representation will be handled in a domain-specific
        # component or view/presentation layer
        new_resource = ResourceModel.create(
            repointed_to=None,
            created_by="user",
        )
        self._session.add(new_resource)
        self._session.flush()
        for model in models:
            model.repointed_to = new_resource.id
        # no need to add the updated models to the session
        # commit happens in the TransactionContext
        return new_resource.as_entity(), tuple(m.as_entity() for m in models)

    def split_resource(self, resource_id: int) -> ResourceEntity: ...
