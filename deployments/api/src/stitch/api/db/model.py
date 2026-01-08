from collections.abc import Sequence
from datetime import datetime
from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    literal,
    select,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declarative_mixin,
    mapped_column,
    relationship,
)
from sqlalchemy.sql import func
from stitch.api.db.mixins import PayloadMixin
from stitch.api.entities import OGSISourcePayload, User as UserEntity

PORTABLE_BIGINT = (
    BigInteger()
    .with_variant(postgresql.BIGINT(), "postgresql")
    .with_variant(sqlite.INTEGER(), "sqlite")
)
PORTABLE_JSON = JSON().with_variant(postgresql.JSONB(), "postgresql")


class Base(DeclarativeBase): ...


@declarative_mixin
class TimestampMixin:
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


@declarative_mixin
class UserAuditMixin:
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    last_updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]
    email: Mapped[str]


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
    country: Mapped[str | None] = mapped_column(String(3), nullable=True)
    # latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    # longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)

    memberships: Mapped[Sequence["MembershipModel"]] = relationship(
        "MembershipModel", back_populates="resource"
    )

    @classmethod
    def create(
        cls,
        created_by: UserEntity,
        name: str | None = None,
        country: str | None = None,
        repointed_to: int | None = None,
        # latitude: float | None = None,
        # longitude: float | None = None,
    ):
        return cls(
            name=name,
            country=country,
            # latitude=latitude,
            # longitude=longitude,
            repointed_to=repointed_to,
            created_by_id=created_by.id,
            last_updated_by_id=created_by.id,
        )

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


class MembershipModel(Base, TimestampMixin):
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
    source: Mapped[str] = mapped_column(String, nullable=False)  # "gem" | "woodmac"
    source_pk: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)

    resource = relationship("ResourceModel", back_populates="memberships")

    @classmethod
    def create(
        cls,
        resource_id: int,
        source: str,
        source_pk: str,
        status: str | None = None,
        created_by: str | None = None,
    ):
        return cls(
            resource_id=resource_id,
            source=source,
            source_pk=source_pk,
            status=status,
            created_by=created_by,
        )

    def copy(self):
        return self.__class__.create(
            resource_id=self.resource_id,
            source_pk=self.source_pk,
            source=self.source,
            created_by=self.created_by,
        )

    # def as_entity(self) -> MembershipEntity:
    #     return MembershipEntity(
    #         id=self.id,
    #         resource_id=self.resource_id,
    #         source=self.source,
    #         source_pk=self.source_pk,
    #         created_by=self.created_by,
    #         status=self.status,
    #         created=self.created,
    #         updated=self.updated,
    #     )
    #


class OGSISource(Base, PayloadMixin[OGSISourcePayload], TimestampMixin):
    __tablename__ = "source_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
