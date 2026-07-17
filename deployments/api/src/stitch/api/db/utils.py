from collections.abc import Collection, Sequence
from functools import reduce
from typing import Any, Protocol

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
from stitch.ogsi.model.og_field import OilGasFieldBase
from stitch.api.db.errors import ResourceIntegrityError

from .model import ResourceModel
from .model.oil_gas_field_source_value import ATTRIBUTE_NAMES, materialize_value
from .queries import coalesced_winner_rows

# Per-field coalesced provenance: field -> (winning value, source key, source id),
# or None when no source carries a value for the field.
type ProvMap = dict[str, tuple[Any, OGSISrcKey, int] | None]


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

    # coalesce_resources builds only the coalesced view + provenance (SQL-side).
    # Detail views also expose the raw per-source rows, so fetch them here.
    rows_by_id = await ResourceModel.source_data_by_resource_id(
        session, [model.id], licensed_sources
    )
    sources = [src for src, _ in rows_by_id.get(model.id, [])]

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
        update={
            "source_data": sources,
            "repointed_to": repointed_to,
            "constituents": constituents,
        }
    )


async def coalesce_resources(
    session: AsyncSession,
    resource_ids: Collection[int],
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> dict[int, OGFieldResource]:
    """Coalesce many resources into one entity each -- coalescing done in SQL.

    The single coalescer behind both the detail and list paths. The winning
    value + provenance for every ``(resource, field)`` is chosen by the SQL
    ranking (``coalesced_winner_rows``); Python only materializes the typed
    value and reads the winning source as provenance -- no priority logic here.
    Returns an entry for every requested id; ids with no active/licensed source
    data (including repointed resources, which the query filters out) yield a
    null-shell view + all-``None`` provenance.

    ``source_data`` is left empty: the coalesced view carries everything the
    list needs, and the detail path attaches raw sources separately (see
    ``resource_model_to_entity``).
    """
    ids = list(dict.fromkeys(resource_ids))
    provenance_by_id: dict[int, ProvMap] = {
        rid: {colname: None for colname in ATTRIBUTE_NAMES} for rid in ids
    }
    if ids:
        rows = await session.execute(coalesced_winner_rows(ids, licensed_sources))
        for rid, colname, value_text, value_num, value_json, source, source_pk in rows:
            value = materialize_value(
                colname,
                value_text=value_text,
                value_num=value_num,
                value_json=value_json,
            )
            provenance_by_id[rid][colname] = (value, source, source_pk)

    out: dict[int, OGFieldResource] = {}
    for rid, provenance in provenance_by_id.items():
        view = OilGasFieldBase(
            **{
                colname: (None if prov is None else prov[0])
                for colname, prov in provenance.items()
            }
        )
        out[rid] = OGFieldResource(
            id=rid,
            source_data=[],
            view=view,
            provenance=provenance,
            constituents=frozenset(),
        )
    return out


def _require_view(resource: OGFieldResource) -> OilGasFieldBase:
    if resource.id is None:
        raise ResourceIntegrityError(
            f"Cannot create view for unmanaged resource: {repr(resource)}"
        )
    if resource.view is None:
        raise ResourceIntegrityError(f"Resource {resource.id} has no coalesced view.")
    return resource.view


def resource_to_view(resource: OGFieldResource) -> OGFieldView:
    view = _require_view(resource)
    return OGFieldView(id=resource.id, **view.model_dump())


def resource_to_list_item_view(resource: OGFieldResource) -> OGFieldListItemView:
    view = _require_view(resource)
    provenance: dict[str, OGSISrcKey | None] = {
        field_name: (None if prov is None else prov[1])
        for field_name, prov in resource.provenance.items()
    }
    return OGFieldListItemView(
        id=resource.id,
        data=view,
        provenance=provenance,
    )


def resource_to_detail_view(resource: OGFieldResource) -> OGFieldDetailView:
    base = resource_to_list_item_view(resource)
    return OGFieldDetailView(
        **base.model_dump(),
        source_data=[
            OG_FIELD_SOURCE_VIEW_ADAPTER.validate_python(source)
            for source in resource.source_data
        ],
    )
