from __future__ import annotations

from collections.abc import Collection, Sequence

from sqlalchemy import (
    ForeignKey,
    Index,
    and_,
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
        """Active ``(source entity, default priority)`` rows per resource id.

        One query mirroring the SQL ``active_src`` CTE: membership -> resource ->
        default priority -> source header, restricted to active memberships of
        non-repointed resources. ``values`` selectin-loads with the entity;
        licensing is applied in SQL. This is the raw source-listing helper for the
        detail path -- it returns the *global default* priority only. Per-field
        override tiering can't be expressed as one scalar per source (a record's
        effective rank now varies by field), so field-scoped ordering lives in the
        SQL ranking (``field_source_values`` / ``queries.add_ranking``), not here.
        Rows are ordered by ``(default priority, source, source_pk)``.
        """
        by_id: dict[int, list[tuple[OGFieldSource, int]]] = {
            rid: [] for rid in resource_ids
        }
        if not by_id:
            return by_id

        m, r, s = MembershipModel, cls, OilGasFieldSourceModel
        p = OGFieldSourcePriority
        stmt = (
            select(m.resource_id, s, p.priority.label("priority"))
            .select_from(m)
            .join(r, r.id == m.resource_id)
            .join(p, p.source == m.source)
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

        stmt = stmt.order_by(p.priority, m.source, s.id)

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
        """Walk ``repointed_id`` upward, tagging every row with its origin input.

        Each row is ``(origin_id, id)``: ``origin_id`` is the input the walk
        started from, ``id`` is a row on the path from that input to its root.
        Carrying ``origin_id`` lets a batch map each input to its own root --
        without it, a multi-input walk returns the *set* of roots and loses which
        input reached which root (see ``root_id_by_resource_id``). Because
        ``repointed_id`` is a single scalar, the graph is a forest: each origin
        traces exactly one path, so ``union_all`` stays correct.
        """
        # Anchor: each input maps to itself.
        parent_tree = (
            select(cls.id.label("origin_id"), cls.id.label("id"))
            .where(cls.id.in_(resource_ids))
            .distinct()
            .cte(name="parent_tree", recursive=True)
        )

        # Recursive term: carry origin_id forward, step one hop up repointed_id.
        # ``select_from(cls)`` is required: the first selected column belongs to
        # the CTE, so without it SQLAlchemy infers the wrong FROM (same reason as
        # the ``select_from(m)`` in ``source_data_by_resource_id`` above).
        ancestors = (
            select(parent_tree.c.origin_id, cls.repointed_id)
            .select_from(cls)
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
        """Select the terminal (non-repointed) rows reachable from the inputs.

        Single-id use only (``get_root``): it selects whole ``cls`` rows and joins
        on ``parent_cte.c.id``, so a multi-input batch that shares a root would
        yield duplicate root rows. For batch input use ``root_id_by_resource_id``,
        which keys results back to each origin.
        """
        parent_cte = cls._parent_tree_cte(*resource_ids)
        return (
            select(cls)
            .join(parent_cte, cls.id == parent_cte.c.id)
            .where(cls.repointed_id.is_(None))
        )

    @classmethod
    async def root_id_by_resource_id(
        cls, session: AsyncSession, resource_ids: Collection[int]
    ) -> dict[int, int]:
        """Map each input id to its terminal (root) resource id, in one query.

        A non-repointed input maps to itself. Mirrors the batch, dict-returning
        convention of ``source_data_by_resource_id``. Used to resolve merged-away
        resources without an N+1 over a candidate list.
        """
        if not resource_ids:
            return {}
        parent_cte = cls._parent_tree_cte(*resource_ids)
        stmt = (
            select(parent_cte.c.origin_id, cls.id)
            .select_from(cls)
            .join(parent_cte, cls.id == parent_cte.c.id)
            .where(cls.repointed_id.is_(None))
        )
        rows = await session.execute(stmt)
        return {origin_id: root_id for origin_id, root_id in rows.all()}
