from collections import defaultdict
from collections.abc import Collection

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from stitch.api.db.model import (
    MembershipModel,
    MembershipStatus,
    MergeCandidateItemModel,
    MergeCandidateModel,
    OilGasFieldSourceValueModel,
    ResourceModel,
)
from stitch.api.entities import MergeCandidateStatus


def _root(parent: dict[int, int], rid: int) -> int:
    while parent[rid] != rid:
        parent[rid] = parent[parent[rid]]
        rid = parent[rid]
    return rid


async def match(
    session: AsyncSession,
    licensed_sources: Collection[str],
) -> list[tuple[int, ...]]:
    m, r = MembershipModel, ResourceModel
    name_v, country_v = (
        aliased(OilGasFieldSourceValueModel),
        aliased(OilGasFieldSourceValueModel),
    )
    rows = await session.execute(
        select(m.resource_id, name_v.value_text, country_v.value_text)
        .select_from(m)
        .join(r, and_(r.id == m.resource_id, r.repointed_id.is_(None)))
        .join(name_v, and_(name_v.source_pk == m.source_pk, name_v.colname == "name"))
        .join(
            country_v,
            and_(country_v.source_pk == m.source_pk, country_v.colname == "country"),
        )
        .where(
            m.status == MembershipStatus.ACTIVE,
            m.source.in_(list(licensed_sources)),
        )
    )
    parent: dict[int, int] = {}
    seed: dict[tuple[str, str], int] = {}
    for resource_id, name, country in rows:
        key = (name.strip().casefold(), country.strip().upper())
        if not key[0] or not key[1]:
            continue
        parent.setdefault(resource_id, resource_id)
        parent[_root(parent, resource_id)] = _root(
            parent, seed.setdefault(key, resource_id)
        )
    components: dict[int, list[int]] = defaultdict(list)
    for resource_id in parent:
        components[_root(parent, resource_id)].append(resource_id)

    denied = await session.execute(
        select(
            MergeCandidateItemModel.merge_candidate_id,
            MergeCandidateItemModel.resource_id,
        )
        .join(
            MergeCandidateModel,
            MergeCandidateModel.id == MergeCandidateItemModel.merge_candidate_id,
        )
        .where(MergeCandidateModel.status == MergeCandidateStatus.DENIED)
    )
    by_candidate: dict[int, set[int]] = defaultdict(set)
    for candidate_id, resource_id in denied:
        by_candidate[candidate_id].add(resource_id)
    blocked: dict[int, set[int]] = defaultdict(set)
    for ids in by_candidate.values():
        for resource_id in ids:
            blocked[resource_id] |= ids - {resource_id}

    groups = []
    for component in components.values():
        kept: list[int] = []
        for resource_id in sorted(component):
            if not blocked[resource_id].intersection(kept):
                kept.append(resource_id)
        if len(kept) >= 2:
            groups.append(tuple(kept))
    return sorted(groups)
