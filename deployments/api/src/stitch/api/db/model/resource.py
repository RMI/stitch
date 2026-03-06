from collections.abc import Sequence
from enum import StrEnum
from sqlalchemy import (
    ForeignKey,
    Index,
    String,
    literal,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship
from stitch.ogsi.model import OGFieldSource, OGSISrcKey

from .oil_gas_field_source import (
    OilGasFieldSourceModel,
)

from stitch.api.entities import Resource, User as UserEntity
from .common import Base
from .mixins import TimestampMixin, UserAuditMixin
from .types import PORTABLE_BIGINT


class MembershipStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    INVALID = "INVALID"


class MembershipModel(TimestampMixin, UserAuditMixin, Base):
    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT, primary_key=True, autoincrement=True
    )
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), nullable=False)
    source: Mapped[OGSISrcKey] = mapped_column(
        String(10), nullable=False
    )  # "gem" | "wm"
    source_pk: Mapped[int] = mapped_column(
        ForeignKey("oil_gas_field_sources.id"), nullable=False
    )
    status: Mapped[MembershipStatus] = mapped_column(
        default=MembershipStatus.ACTIVE, nullable=False
    )

    @classmethod
    def create(
        cls,
        created_by: UserEntity,
        resource: "ResourceModel",
        source: OGSISrcKey,
        source_pk: int,
        status: MembershipStatus = MembershipStatus.ACTIVE,
    ):
        model = cls(
            resource_id=resource.id,
            source=source,
            source_pk=source_pk,
            status=status,
            created_by_id=created_by.id,
            last_updated_by_id=created_by.id,
        )
        return model

    def copy(self):
        return self.__class__(
            resource_id=self.resource_id,
            source=self.source,
            source_pk=self.source_pk,
            status=self.status,
            created=self.created,
            updated=self.updated,
            created_by_id=self.created_by_id,
            last_updated_by_id=self.last_updated_by_id,
        )


class ResourceModel(TimestampMixin, UserAuditMixin, Base):
    __tablename__ = "resources"
    __table_args__ = (Index("rp_repointed_id_idx", "repointed_id"),)

    id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT, primary_key=True, autoincrement=True
    )
    repointed_id: Mapped[int | None] = mapped_column(
        PORTABLE_BIGINT, ForeignKey("resources.id"), nullable=True
    )
    name: Mapped[str | None] = mapped_column(String, nullable=True)

    # SQLAlchemy will automatically see the foreign key `memberships.resource_id`
    # and configure the appropriate SQL statement to load the membership objects
    memberships: Mapped[list[MembershipModel]] = relationship()

    def as_empty_entity(self):
        return Resource(
            id=self.id,
            name=self.name,
            source_data=[],
            constituents=[],
            created=self.created,
            updated=self.updated,
        )

    async def get_source_data(self, session: AsyncSession) -> Sequence[OGFieldSource]:
        source_pks = [
            mem.source_pk
            for mem in self.memberships
            if mem.status == MembershipStatus.ACTIVE
        ]
        stmt = select(OilGasFieldSourceModel).where(
            OilGasFieldSourceModel.id.in_(source_pks)
        )
        sources = (await session.scalars(stmt)).all()
        return [ofgsm.as_entity() for ofgsm in sources]

    async def get_root(self, session: AsyncSession):
        root = await session.scalar(self.__class__._root_select(self.id))
        if root is None:
            # TODO: add specific errors & exceptions
            raise
        return root

    async def get_constituents(self, session: AsyncSession):
        return await self.__class__.get_constituents_by_root_id(session, self.id)

    @classmethod
    def create(
        cls,
        created_by: UserEntity,
        name: str | None = None,
        repointed_to: int | None = None,
    ):
        return cls(
            name=name,
            repointed_id=repointed_to,
            created_by_id=created_by.id,
            last_updated_by_id=created_by.id,
        )

    @classmethod
    async def get_constituents_by_root_id(
        cls, session: AsyncSession, root_resource_id: int
    ):
        sub_cte = cls._subtree_cte(resource_id=root_resource_id)
        stmt = select(cls).join(sub_cte, cls.id == sub_cte.c.id)
        return (await session.scalars(stmt)).all()

    @classmethod
    def _parent_tree_cte(cls, *resource_ids: int):
        parent_tree = (
            select(cls.id)
            .where(cls.id.in_(resource_ids))
            .distinct()
            .cte(name="parent_tree", recursive=True)
        )

        ancestors = (
            select(cls.repointed_id)
            .join(parent_tree, cls.id == parent_tree.c.id)
            .where(cls.repointed_id.is_not(None))
        )
        return parent_tree.union_all(ancestors)

    @classmethod
    def _subtree_cte(cls, resource_id: int):
        subtree = (
            select(cls.id)
            .where(cls.id == resource_id)
            .cte(name="subtree", recursive=True)
        )

        children = select(cls.id).join(subtree, cls.repointed_id == subtree.c.id)
        return subtree.union_all(children)

    @classmethod
    def _complete_tree_cte(cls, resource_id: int):
        resolved = select(literal(resource_id).label("id")).cte(
            name="resolved", recursive=True
        )
        children = select(cls.id).join(resolved, cls.repointed_id == resolved.c.id)
        parents = (
            select(cls.repointed_id)
            .join(resolved, cls.id == resolved.c.id)
            .where(cls.repointed_id.is_not(None))
        )

        return resolved.union(children, parents)

    @classmethod
    def _root_select(cls, *resource_ids: int):
        parent_cte = cls._parent_tree_cte(*resource_ids)
        return (
            select(cls)
            .join(parent_cte, cls.id == parent_cte.c.id)
            .where(cls.repointed_id.is_(None))
        )
