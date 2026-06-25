from collections.abc import Collection, Sequence
from functools import reduce
from typing import Protocol

from pydantic import TypeAdapter
from sqlalchemy import and_, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from stitch.ogsi.model import (
    OGFieldDetailView,
    OGFieldListItemView,
    OGFieldResource,
    OGFieldSource,
    OGFieldSourceView,
    OGFieldView,
    OGSISrcKey,
)
from stitch.ogsi.model.og_field import OilGasFieldBase
from stitch.api.coalesce import ProvAttrs, coalesce_og_field_resource
from stitch.api.db.errors import ResourceIntegrityError

from .model import (
    OGFieldResourceSourcePriority,
    OGFieldSourcePriority,
    ResourceModel,
)


OG_FIELD_SOURCE_VIEW_ADAPTER = TypeAdapter(OGFieldSourceView)


class Identified(Protocol):
    @property
    def id(self) -> int | None: ...


def partition_by_id_none[T: Identified](
    items: Sequence[T],
) -> tuple[Sequence[T], Sequence[T]]:
    def _reducer(acc: tuple[list[T], list[T]], curr: T):
        new_, existing = acc
        if curr.id is None:
            return ([*new_, curr], existing)
        else:
            return (new_, [*existing, curr])

    return reduce(_reducer, items, ([], []))


async def resource_model_to_entity(
    session: AsyncSession,
    model: ResourceModel,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> OGFieldResource:
    repointed = model.repointed_id is not None
    view, provenance, src_data = (
        await coalesce_resources(
            session,
            [model.id],
            licensed_sources,
            repointed_ids=[model.id] if repointed else (),
        )
    )[model.id]

    constituent_models = await ResourceModel.get_constituents_by_root_id(
        session, model.id
    )
    constituents = [
        cm.as_empty_entity() for cm in constituent_models if cm.id != model.id
    ]
    rep_res: OGFieldResource | None = None
    if repointed:
        rep_model = await session.get(ResourceModel, model.repointed_id)
        rep_res = rep_model.as_empty_entity() if rep_model else None

    return OGFieldResource(
        id=model.id,
        repointed_to=None if rep_res is None else rep_res.id,
        constituents=frozenset([cm.id for cm in constituents if cm.id is not None]),
        source_data=src_data,
        view=view,
        provenance=provenance,
    )


async def _effective_priorities_by_resource_id(
    session: AsyncSession, resource_ids: Collection[int]
) -> dict[int, list[OGSISrcKey]]:
    """Override-aware source priority order per resource, best-first.

    One query: every (resource, source) pair via resources × the priority table,
    left-joined to the per-resource override, ordered by COALESCE(override,
    default) then source -- the same expression/ordering ``build_coalesced_values``
    uses, so the Python winner matches the SQL winner.
    """
    by_id: dict[int, list[OGSISrcKey]] = {rid: [] for rid in resource_ids}
    if not by_id:
        return by_id

    r = ResourceModel
    p = OGFieldSourcePriority
    o = OGFieldResourceSourcePriority
    effective = func.coalesce(o.priority, p.priority)
    stmt = (
        select(r.id, p.source)
        .select_from(r)
        .join(p, true())  # cross join: every (resource, source) pair
        .outerjoin(o, and_(o.resource_id == r.id, o.source == p.source))
        .where(r.id.in_(by_id.keys()))
        .order_by(r.id, effective.asc(), p.source.asc())
    )
    for resource_id, source in (await session.execute(stmt)).all():
        by_id[resource_id].append(source)
    return by_id


def _coalesce_view(
    src_data: Sequence[OGFieldSource],
    priorities: Sequence[OGSISrcKey],
    *,
    repointed: bool,
) -> tuple[OilGasFieldBase, ProvAttrs]:
    # A repointed resource contributes no values (parity with the SQL CTE's
    # `repointed_id IS NULL` filter): coalesce over an empty list -> null-shell.
    coalescing_input = [] if repointed else src_data
    # Keep only sources with a priority row (mirrors the SQL inner join on
    # og_field_source_priority) and sort by source_pk descending so that, under
    # coalesce_og_field_resource's stable reverse-priority re-sort + last-wins
    # reduce, the lowest source_pk wins among duplicate same-source records
    # (matches the SQL `source_pk ASC` final tiebreak).
    prepared = sorted(
        (s for s in coalescing_input if s.source in priorities),
        key=lambda s: s.id,
        reverse=True,
    )
    return coalesce_og_field_resource(prepared, priorities)


async def coalesce_resources(
    session: AsyncSession,
    resource_ids: Collection[int],
    licensed_sources: Collection[OGSISrcKey] | None = None,
    *,
    repointed_ids: Collection[int] = frozenset(),
) -> dict[int, tuple[OilGasFieldBase, ProvAttrs, list[OGFieldSource]]]:
    """Coalesce many resources in Python from batched source data + priorities.

    The single coalescer behind both the detail and list paths. Returns an entry
    for every requested id; ids with no active/licensed source data (or listed in
    ``repointed_ids``) yield a null-shell view + all-``None`` provenance.
    """
    src_by_id = await ResourceModel.source_data_by_resource_id(
        session, resource_ids, licensed_sources
    )
    prio_by_id = await _effective_priorities_by_resource_id(session, resource_ids)
    repointed = set(repointed_ids)

    out: dict[int, tuple[OilGasFieldBase, ProvAttrs, list[OGFieldSource]]] = {}
    for rid in resource_ids:
        src = src_by_id.get(rid, [])
        view, provenance = _coalesce_view(
            src, prio_by_id.get(rid, []), repointed=rid in repointed
        )
        out[rid] = (view, provenance, src)
    return out


def resource_to_view(resource: OGFieldResource, force_coalesce: bool = False):
    if resource.id is None:
        raise ResourceIntegrityError(
            f"Cannot create view for unmanaged resource: {repr(resource)}"
        )

    view = (
        coalesce_og_field_resource(resource.source_data)[0]
        if force_coalesce or resource.view is None
        else resource.view
    )

    return OGFieldView(id=resource.id, **view.model_dump())


def resource_to_list_item_view(
    resource: OGFieldResource, force_coalesce: bool = False
) -> OGFieldListItemView:
    if resource.id is None:
        raise ResourceIntegrityError(
            f"Cannot create view for unmanaged resource: {repr(resource)}"
        )

    if force_coalesce or resource.view is None:
        data, raw_provenance = coalesce_og_field_resource(resource.source_data)
    else:
        data = resource.view
        raw_provenance = resource.provenance

    provenance: dict[str, OGSISrcKey | None] = {
        field_name: (None if prov is None else prov[1])
        for field_name, prov in raw_provenance.items()
    }

    return OGFieldListItemView(
        id=resource.id,
        data=data,
        provenance=provenance,
    )


def resource_to_detail_view(
    resource: OGFieldResource, force_coalesce: bool = False
) -> OGFieldDetailView:
    base = resource_to_list_item_view(resource, force_coalesce=force_coalesce)
    return OGFieldDetailView(
        **base.model_dump(),
        source_data=[
            OG_FIELD_SOURCE_VIEW_ADAPTER.validate_python(source)
            for source in resource.source_data
        ],
    )
