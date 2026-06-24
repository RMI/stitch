from collections.abc import Collection, Sequence
from functools import reduce
from typing import Protocol

from pydantic import TypeAdapter
from sqlalchemy import and_, func, select
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
    src_data = await model.get_source_data(session)
    # Write paths must pass licensed_sources=None: the returned entity
    # feeds back into resource construction and must not be redacted.
    if licensed_sources is not None:
        src_data = [s for s in src_data if s.source in licensed_sources]
    constituent_models = await ResourceModel.get_constituents_by_root_id(
        session, model.id
    )
    constituents = [
        cm.as_empty_entity() for cm in constituent_models if cm.id != model.id
    ]
    rep_res: OGFieldResource | None = None
    if model.repointed_id is not None:
        rep_model = await session.get(ResourceModel, model.repointed_id)
        rep_res = rep_model.as_empty_entity() if rep_model else None

    # Coalesce in Python over the already-loaded (licensed-filtered) src_data,
    # using this resource's effective, override-aware source priorities.
    priorities = await _effective_source_priorities(session, model.id)
    # A repointed resource contributes no values (parity with the SQL CTE's
    # `repointed_id IS NULL` filter): coalesce over an empty list -> null-shell.
    coalescing_input = [] if model.repointed_id is not None else src_data
    # Keep only sources with a priority row (mirrors the SQL inner join on
    # og_field_source_priority) and sort by source_pk descending so that, under
    # coalesce_og_field_resource's stable reverse-priority re-sort + last-wins
    # reduce, the lowest source_pk wins among duplicate same-source records
    # (matches the SQL `source_pk ASC` final tiebreak).
    prepared_src_data = sorted(
        (s for s in coalescing_input if s.source in priorities),
        key=lambda s: s.id,
        reverse=True,
    )
    view, provenance = coalesce_og_field_resource(prepared_src_data, priorities)

    return OGFieldResource(
        id=model.id,
        repointed_to=None if rep_res is None else rep_res.id,
        constituents=frozenset([cm.id for cm in constituents if cm.id is not None]),
        source_data=src_data,
        view=view,
        provenance=provenance,
    )


async def _effective_source_priorities(
    session: AsyncSession, resource_id: int
) -> list[OGSISrcKey]:
    """Source keys for ``resource_id``, best-first, override-aware.

    The same ``COALESCE(per-resource override, default)`` priority expression and
    ``(priority, source)`` ordering the list path's ``build_coalesced_values``
    uses -- reading the DB as the authoritative source of priorities and folding
    in per-resource overrides in one light query.
    """
    p, o = OGFieldSourcePriority, OGFieldResourceSourcePriority
    effective = func.coalesce(o.priority, p.priority)
    stmt = (
        select(p.source)
        .select_from(p)
        .outerjoin(o, and_(o.source == p.source, o.resource_id == resource_id))
        .order_by(effective.asc(), p.source.asc())  # ties broken by source name
    )
    return list((await session.scalars(stmt)).all())


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
