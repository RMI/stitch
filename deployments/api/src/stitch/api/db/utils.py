from collections.abc import Collection, Iterable, Sequence
from functools import reduce
from typing import Any, Protocol

from pydantic import TypeAdapter
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
from stitch.api.db.errors import ResourceIntegrityError

from .model import ResourceModel
from .model.oil_gas_field_source_value import ATTRIBUTE_NAMES, materialize_value
from .queries import coalesced_candidate_rows, coalesced_winner_rows

# Per-field coalesced provenance: field -> (winning value, source key, source id),
# or None when no source carries a value for the field.
type ProvMap = dict[str, tuple[Any, OGSISrcKey, int] | None]

# One flat ``rn == 1`` winner row: (colname, value_text, value_num, value_json,
# source, source_pk). The ranking is done in SQL; these carry the chosen value.
type WinnerRow = tuple[str, Any, Any, Any, OGSISrcKey, int]


OG_FIELD_SOURCE_VIEW_ADAPTER = TypeAdapter(OGFieldSourceView)
OG_FIELD_SOURCE_ADAPTER = TypeAdapter(OGFieldSource)


def _view_and_provenance(
    winner_rows: Iterable[WinnerRow],
) -> tuple[OilGasFieldBase, ProvMap]:
    """Build the coalesced view + provenance from already-ranked winner rows.

    ``winner_rows`` is the ``rn == 1`` set (one row per field). The ranking --
    the coalescing decision -- already happened in SQL; this only materializes
    the typed value and records the winning source as provenance. Fields with no
    winning row stay ``None``.
    """
    provenance: ProvMap = {colname: None for colname in ATTRIBUTE_NAMES}
    for colname, value_text, value_num, value_json, source, source_pk in winner_rows:
        provenance[colname] = (
            materialize_value(
                colname,
                value_text=value_text,
                value_num=value_num,
                value_json=value_json,
            ),
            source,
            source_pk,
        )
    view = OilGasFieldBase(
        **{
            colname: (None if prov is None else prov[0])
            for colname, prov in provenance.items()
        }
    )
    return view, provenance


def _source_data_from_rows(rows: Sequence[Any]) -> list[OGFieldSource]:
    """Rebuild the raw per-source entities from ranked candidate rows.

    Groups the flat rows by ``source_pk`` (rank ignored -- every candidate row is
    kept, not just winners) and reassembles each source's ``{field: value}`` plus
    its ``source``/``source_record`` header. Rows arrive best-priority-first, so
    the result is source-priority-ordered, matching the old listing.

    A source carrying no value rows never appears here (it contributes no rows);
    that matches "unset == absent" and differs only for the degenerate case of a
    source with zero values.
    """
    by_source: dict[int, dict[str, Any]] = {}
    for r in rows:
        entry = by_source.get(r.source_pk)
        if entry is None:
            # Dense shape: seed every attribute to None (the long table is sparse,
            # and the entity requires each field present), then fill what exists.
            entry = {colname: None for colname in ATTRIBUTE_NAMES}
            entry.update(
                id=r.source_pk,
                source=r.source,
                source_record=r.source_record,
            )
            by_source[r.source_pk] = entry
        entry[r.colname] = materialize_value(
            r.colname,
            value_text=r.value_text,
            value_num=r.value_num,
            value_json=r.value_json,
        )
    return [
        OG_FIELD_SOURCE_ADAPTER.validate_python(entry) for entry in by_source.values()
    ]


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
    """Build the full detail entity for one resource in a SINGLE query.

    ``coalesced_candidate_rows`` returns every ranked value row for the resource
    (winner-first) joined to its source header. From that one result we derive
    both the coalesced view + provenance (the ``rn == 1`` rows) and the raw
    ``source_data`` (all rows, grouped by source). This replaces the former
    winner-query + ``source_data_by_resource_id`` pair: one DB round-trip, and
    the SQL ranking stays the only coalescer -- the ``rn == 1`` cut is a filter
    on a rank SQL already computed, not a second coalesce.
    """
    rows = (
        await session.execute(coalesced_candidate_rows([model.id], licensed_sources))
    ).all()
    winner_rows: list[WinnerRow] = [
        (r.colname, r.value_text, r.value_num, r.value_json, r.source, r.source_pk)
        for r in rows
        if r.rn == 1
    ]
    view, provenance = _view_and_provenance(winner_rows)
    source_data = _source_data_from_rows(rows)

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

    return OGFieldResource(
        id=model.id,
        view=view,
        provenance=provenance,
        source_data=source_data,
        repointed_to=repointed_to,
        constituents=constituents,
    )


async def coalesce_resources(
    session: AsyncSession,
    resource_ids: Collection[int],
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> dict[int, OGFieldResource]:
    """Coalesce many resources into one entity each -- coalescing done in SQL.

    The list-path coalescer: the winning value + provenance for every
    ``(resource, field)`` is chosen by the SQL ranking (``coalesced_winner_rows``);
    Python only materializes the typed value and reads the winning source as
    provenance -- no priority logic here. Returns an entry for every requested id;
    ids with no active/licensed source data (including repointed resources, which
    the query filters out) yield a null-shell view + all-``None`` provenance.

    ``source_data`` is left empty: the list only needs the coalesced view, so it
    never pays to hydrate the raw rows. The detail path builds view *and*
    ``source_data`` from one query instead (see ``resource_model_to_entity``).
    """
    ids = list(dict.fromkeys(resource_ids))
    winners_by_id: dict[int, list[WinnerRow]] = {rid: [] for rid in ids}
    if ids:
        rows = await session.execute(coalesced_winner_rows(ids, licensed_sources))
        for rid, colname, value_text, value_num, value_json, source, source_pk in rows:
            winners_by_id[rid].append(
                (colname, value_text, value_num, value_json, source, source_pk)
            )

    out: dict[int, OGFieldResource] = {}
    for rid in ids:
        view, provenance = _view_and_provenance(winners_by_id[rid])
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
