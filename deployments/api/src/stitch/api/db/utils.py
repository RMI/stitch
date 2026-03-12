from collections.abc import Sequence
from functools import reduce
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession
from stitch.ogsi.model import OGFieldView
from stitch.api.coalesce import coalesce_og_field_resource
from stitch.api.db.errors import ResourceIntegrityError
from stitch.ogsi.model import OGFieldResource

from .model import ResourceModel


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
    session: AsyncSession, model: ResourceModel
) -> OGFieldResource:
    src_data = await model.get_source_data(session)
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

    view, provenance = coalesce_og_field_resource(src_data)

    return OGFieldResource(
        id=model.id,
        repointed_to=None if rep_res is None else rep_res.id,
        constituents=frozenset([cm.id for cm in constituents if cm.id is not None]),
        source_data=src_data,
        view=view,
        provenance=provenance,
    )


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
