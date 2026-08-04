from __future__ import annotations

from collections.abc import Collection, Sequence

from sqlalchemy import (
    ForeignKey,
    Index,
    and_,
    func,
    literal,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship
from stitch.api.db.errors import ResourceNotFoundError
from stitch.ogsi.model import OGFieldSource, OGFieldResource
from stitch.ogsi.model.types import OGSISrcKey

from .membership import MembershipModel, MembershipStatus
from .oil_gas_field_source import OilGasFieldSourceModel
from .og_field_source_priority import OGFieldSourcePriority
from .og_field_resource_source_priority import OGFieldResourceSourcePriority

from stitch.api.entities import User as UserEntity
from .common import Base
from .mixins import TimestampMixin, UserAuditMixin
from .types import PORTABLE_BIGINT


class ResourceModel(TimestampMixin, UserAuditMixin, Base):
    __tablename__ = "og_field_resources"
    __table_args__ = (Index("rp_repointed_id_idx", "repointed_id"),)

    id: Mapped[int] = mapped_column(
        PORTABLE_BIGINT, primary_key=True, autoincrement=True
    )
    repointed_id: Mapped[int | None] = mapped_column(
        PORTABLE_BIGINT, ForeignKey("og_field_resources.id"), nullable=True
    )

    # SQLAlchemy will automatically see the foreign key `memberships.resource_id`
    # and configure the appropriate SQL statement to load the membership objects
    memberships: Mapped[list[MembershipModel]] = relationship()

    def as_empty_entity(self):
        return OGFieldResource(
            id=self.id,
            source_data=[],
            constituents=frozenset(),
        )

    @classmethod
    async def source_data_by_resource_id(
        cls,
        session: AsyncSession,
        resource_ids: Collection[int],
        licensed_sources: Collection[OGSISrcKey] | None = None,
    ) -> dict[int, list[tuple[OGFieldSource, int]]]:
        """Active ``(source entity, effective priority)`` rows per resource id.

        One query mirroring the SQL ``active_src`` CTE: membership -> resource ->
        priority (+ per-resource override) -> source header, restricted to active
        memberships of non-repointed resources. ``values`` selectin-loads with the
        entity. Effective priority is ``COALESCE(override, default)``; licensing is
        applied in SQL. Rows are ordered best-priority-first, matching the coalesce
        ranking (``queries.add_ranking``).
        """
        by_id: dict[int, list[tuple[OGFieldSource, int]]] = {
            rid: [] for rid in resource_ids
        }
        if not by_id:
            return by_id

        m, r, s = MembershipModel, cls, OilGasFieldSourceModel
        p, o = OGFieldSourcePriority, OGFieldResourceSourcePriority
        priority = func.coalesce(o.priority, p.priority)
        stmt = (
            select(m.resource_id, s, priority.label("priority"))
            .select_from(m)
            .join(r, r.id == m.resource_id)
            .join(p, p.source == m.source)
            .outerjoin(o, and_(o.resource_id == r.id, o.source == m.source))
            # dual-key: membership.source is not FK-tied to the header's source,
            # so matching on source_pk alone could admit a mismatched row.
            .join(s, and_(s.id == m.source_pk, s.source == m.source))
            .where(
                r.repointed_id.is_(None),
                m.status == MembershipStatus.ACTIVE,
                m.resource_id.in_(by_id.keys()),
            )
        )
        if licensed_sources is not None:
            stmt = stmt.where(m.source.in_(list(dict.fromkeys(licensed_sources))))

        # Best-priority first, matching the coalesce ranking
        # (queries.add_ranking): (priority, source, source_pk). Callers that want
        # winner-first order (field_source_values) can rely on this instead of a
        # separate Python sort.
        stmt = stmt.order_by(priority, m.source, s.id)

        for resource_id, src_model, prio in (await session.execute(stmt)).all():
            by_id[resource_id].append((src_model.as_entity(), prio))
        return by_id

    async def get_source_data(self, session: AsyncSession) -> Sequence[OGFieldSource]:
        by_id = await type(self).source_data_by_resource_id(session, [self.id])
        return [src for src, _ in by_id[self.id]]

    async def get_root(self, session: AsyncSession):
        root = await session.scalar(self.__class__._root_select(self.id))
        if root is None:
            raise ResourceNotFoundError(
                f"No root ResourceModel found for `{repr(self)}`"
            )
        return root

    async def get_constituents(self, session: AsyncSession):
        return await self.__class__.get_constituents_by_root_id(session, self.id)

    @classmethod
    def create(
        cls,
        created_by: UserEntity,
        repointed_to: int | None = None,
    ):
        return cls(
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
