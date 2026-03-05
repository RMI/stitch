from collections import defaultdict
from enum import StrEnum
from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    literal,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .sources import (
    SOURCE_TABLES,
    SourceKey,
    SourceModel,
    SourceModelData,
)

from stitch.models.types import IdType
from stitch.api.entities import User as UserEntity
from .common import Base
from .mixins import TimestampMixin, UserAuditMixin
from .types import PORTABLE_BIGINT


class MembershipStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    INVALID = "INVALID"


class MembershipModel(TimestampMixin, UserAuditMixin, Base):
    __tablename__ = "memberships"

    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            "source",
            "source_pk",
            name="uc_source_source_pk",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), nullable=False)
    source: Mapped[SourceKey] = mapped_column(
        String(10), nullable=False
    )  # "gem" | "wm"
    source_pk: Mapped[int] = mapped_column(PORTABLE_BIGINT, nullable=False)
    status: Mapped[MembershipStatus]

    @classmethod
    def create(
        cls,
        created_by: UserEntity,
        resource: "ResourceModel",
        source: SourceKey,
        source_pk: IdType,
        status: MembershipStatus = MembershipStatus.ACTIVE,
    ):
        model = cls(
            resource_id=resource.id,
            source=source,
            source_pk=str(source_pk),
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

    async def get_source_data(self, session: AsyncSession):
        pks_by_src: dict[SourceKey, set[int]] = defaultdict(set)
        for mem in self.memberships:
            if mem.status == MembershipStatus.ACTIVE:
                pks_by_src[mem.source].add(mem.source_pk)

        results: dict[SourceKey, dict[IdType, SourceModel]] = defaultdict(dict)
        for src, pks in pks_by_src.items():
            model_cls = SOURCE_TABLES.get(src)
            if model_cls is None:
                continue
            stmt = select(model_cls).where(model_cls.id.in_(pks))
            for src_model in await session.scalars(stmt):
                results[src][src_model.id] = src_model

        return SourceModelData(**results)

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
