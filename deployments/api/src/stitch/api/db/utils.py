from collections.abc import Collection, Sequence
from functools import reduce
from typing import Protocol

from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession
from stitch.ogsi.model import (
    OGFieldDetailView,
    OGFieldListItemView,
    OGFieldResource,
    OGFieldSourceView,
    OGFieldView,
    OGSISrcKey,
)
from stitch.api.coalesce import coalesce_og_field_resource
from stitch.api.db.errors import ResourceIntegrityError

from .model import ResourceModel


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
    base = (await coalesce_resources(session, [model.id], licensed_sources))[model.id]

    constituent_models = await ResourceModel.get_constituents_by_root_id(
        session, model.id
    )
    constituents = frozenset(
        cm.id for cm in constituent_models if cm.id is not None and cm.id != model.id
    )
    repointed_to: int | None = None
    if model.repointed_id is not None:
        rep_model = await session.get(ResourceModel, model.repointed_id)
        repointed_to = rep_model.id if rep_model else None

    return base.model_copy(
        update={"repointed_to": repointed_to, "constituents": constituents}
    )


async def coalesce_resources(
    session: AsyncSession,
    resource_ids: Collection[int],
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> dict[int, OGFieldResource]:
    """Coalesce many resources in Python into one entity each.

    The single place that builds an ``OGFieldResource`` from coalesced parts,
    behind both the detail and list paths. Returns an entry for every requested
    id; ids with no active/licensed source data -- including repointed resources,
    which ``source_data_by_resource_id`` filters out -- yield a null-shell view +
    all-``None`` provenance.
    """
    rows_by_id = await ResourceModel.source_data_by_resource_id(
        session, resource_ids, licensed_sources
    )

    out: dict[int, OGFieldResource] = {}
    for rid in resource_ids:
        rows = rows_by_id.get(rid, [])
        # Effective priority order, best-first; built from only the sources
        # present, so coalesce_og_field_resource's priorities.index never raises.
        prio_map = {src.source: prio for src, prio in rows}
        priorities = sorted(prio_map, key=lambda k: (prio_map[k], k))
        sources = [src for src, _ in rows]
        view, provenance = coalesce_og_field_resource(sources, priorities)
        out[rid] = OGFieldResource(
            id=rid,
            source_data=sources,
            view=view,
            provenance=provenance,
            constituents=frozenset(),
        )
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
