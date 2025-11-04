from datetime import datetime
from functools import reduce
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from stitch.core.resources.adapters.sql.model.membership import MembershipModel
from stitch.core.resources.domain.entities import MembershipEntity
from stitch.core.resources.domain.ports import MembershipRepository


class SQLMembershipRepository(MembershipRepository):
    _session: Session

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self, resource_id: int, source_name: str, source_id: str
    ):
        model = MembershipModel(
            resource_id=resource_id,
            dataset=source_name,
            source_pk=source_id,
        )

        self._session.add(model)
        self._session.flush()
        return model.id

    def get(self, membership_id: int) -> MembershipEntity | None:
        model = self._session.get(MembershipModel, membership_id)
        if model is None:
            return None
        return self._model_to_entity(model)

    def get_active_members(self, resource_id: int) -> Sequence[MembershipModel]:
        stmt = select(MembershipModel).where(MembershipModel.resource_id == resource_id)

        return self._session.execute(stmt).scalars().all()

    def _model_to_entity(self, model: MembershipModel) -> MembershipEntity:
        return MembershipEntity(
            id=model.id,
            resource_id=model.resource_id,
            dataset=model.dataset,
            source_pk=model.source_pk,
            created_by=model.created_by,
            status=model.status,
            created=model.created,
        )
