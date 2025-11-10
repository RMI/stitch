from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from stitch.core.resources.adapters.sql.model.membership import MembershipModel
from stitch.core.resources.domain.entities import MembershipEntity
from stitch.core.resources.domain.ports import MembershipRepository


class SQLMembershipRepository(MembershipRepository):
    _session: Session

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, resource_id: int, source: str, source_pk: str):
        model = MembershipModel(
            resource_id=resource_id,
            source=source,
            source_pk=source_pk,
        )

        self._session.add(model)
        self._session.flush()
        return model.id

    def get(self, membership_id: int) -> MembershipEntity | None:
        model = self._session.get(MembershipModel, membership_id)
        if model is None:
            return None
        return model.as_entity()

    def get_active_members(self, resource_id: int) -> Sequence[MembershipModel]:
        stmt = select(MembershipModel).where(MembershipModel.resource_id == resource_id)

        return self._session.execute(stmt).scalars().all()
