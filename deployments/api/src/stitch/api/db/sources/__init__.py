from collections import defaultdict
from collections.abc import Mapping, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from stitch.api.db.model import MembershipModel
from .models import SOURCE_TABLES, SourceKey, SourceModel


async def get_sources_from_memberships(
    session: AsyncSession, memberships: Sequence[MembershipModel]
) -> Mapping[tuple[SourceKey, str], SourceModel]:
    pks_by_src: dict[SourceKey, set[int]] = defaultdict(set)
    for mem in memberships:
        pks_by_src[mem.source].add(int(mem.source_pk))  # pyright: ignore[reportArgumentType]

    results: dict[tuple[SourceKey, str], SourceModel] = {}
    for src, pk in pks_by_src.items():
        model_cls = SOURCE_TABLES.get(src)
        if model_cls is None:
            continue
        stmt = select(model_cls).where(model_cls.id.in_(pk))
        for src_model in await session.scalars(stmt):
            results[(src, str(src_model.id))] = src_model

    return results
