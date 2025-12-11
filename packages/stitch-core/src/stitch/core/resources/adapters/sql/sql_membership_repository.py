from collections import defaultdict
from collections.abc import Mapping
from functools import reduce
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from stitch.core.resources.adapters.sql.common import extract_id
from stitch.core.resources.adapters.sql.errors import MembershipIntegrityError
from stitch.core.resources.adapters.sql.model.membership import MembershipModel
from stitch.core.resources.domain.entities import (
    MembershipEntity,
    ResourceEntity,
    UserPlaceholder,
)
from stitch.core.resources.domain.ports import MembershipRepository


class SQLMembershipRepository(MembershipRepository):
    _session: Session

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        resource_id: int,
        source: str,
        source_pk: str,
        status: str | None = None,
        created_by: UserPlaceholder | None = None,
    ) -> int:
        model = MembershipModel(
            resource_id=resource_id,
            source=source,
            source_pk=source_pk,
            status=status,
            created_by=created_by,
        )

        self._session.add(model)
        self._session.flush()
        return model.id

    def get(self, membership_id: int) -> MembershipEntity | None:
        model = self._session.get(MembershipModel, membership_id)
        if model is None:
            return None
        return model.as_entity()

    def get_active_members(self, resource_id: int):
        stmt = select(MembershipModel).where(MembershipModel.resource_id == resource_id)

        return tuple(m.as_entity() for m in self._session.execute(stmt).scalars().all())

    def get_source_refs(self, resource_id: int) -> Mapping[str, Sequence[str]]:
        def _reducer(map_: dict[str, list[str]], m: MembershipEntity):
            map_[m.source].append(m.source_pk)
            return map_

        return reduce(_reducer, self.get_active_members(resource_id), defaultdict(list))

    def create_repointed_memberships(
        self,
        from_resources: Sequence[ResourceEntity | int],
        to_resource: ResourceEntity | int,
    ) -> Sequence[MembershipEntity]:
        """Create new memberships pointing to a different resource.

        Collect all memberships whose `resource_id` is in the `from_resoure_ids` argument. For each of these, create
        a new membership where `resource_id` = `to_resource_id`.

        This all takes place after a `merge_resources` operation where a new ResourceModel is created.

        Args:
            from_resoure_ids: the original resource_ids
            to_resource_id: the new resource id

        Returns:
            Sequence of newly created `MembershipEntity` objects.
        """
        from_ids = [extract_id(res) for res in from_resources]
        to_id = extract_id(to_resource)

        target_memberships = self._session.scalars(
            select(MembershipModel).where(MembershipModel.resource_id == to_id)
        ).all()
        if target_memberships:
            raise MembershipIntegrityError(
                (
                    f"Target resource (id={to_id}) already has memberships. "
                    + "Cannot repoint to a resource with existing memberships."
                )
            )

        existing_memberships = self._session.scalars(
            select(MembershipModel).where(MembershipModel.resource_id.in_(from_ids))
        ).all()
        if any((mem.status is not None for mem in existing_memberships)):
            invalid = filter(lambda m: m.status is not None, existing_memberships)
            repr_ = f"({','.join(map(repr, invalid))})"
            raise MembershipIntegrityError(
                f"Cannot repoint memberships that have already been repointed. {repr_}"
            )

        def _model_factory(to_id: int):
            def _fn(m: MembershipModel):
                nonlocal to_id
                return MembershipModel.create(
                    resource_id=to_id,
                    source_pk=m.source_pk,
                    source=m.source,
                    status=None,
                    created_by="user",
                )

            return _fn

        new_memberships = list(
            map(
                _model_factory(to_id=to_id),
                existing_memberships,
            )
        )
        self._session.add_all(new_memberships)
        self._session.flush()
        return [m.as_entity() for m in new_memberships]
