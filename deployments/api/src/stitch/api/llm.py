from __future__ import annotations

from collections.abc import Collection
from sqlalchemy.ext.asyncio import AsyncSession
from stitch.api.db import og_field_resource_actions
from stitch.api.db.utils import resource_to_detail_view
from stitch.ogsi.model import OGFieldDetailView, OGSISrcKey
from stitch_core_llm import suggest_missing_field_values
from stitch_core_llm.model import FieldSuggestion
from stitch_core_llm.typings import ALL_SUGGESTION_FIELDS, AllowedSuggestionField


async def _load_suggestion_context(
    *,
    session: AsyncSession,
    resource_id: int,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> OGFieldDetailView:
    resource = await og_field_resource_actions.get_resolved(
        session=session, id=resource_id, licensed_sources=licensed_sources
    )
    return resource_to_detail_view(resource)


async def og_suggest_missing_field_values(
    *,
    session: AsyncSession,
    resource_id: int,
    fields: Collection[AllowedSuggestionField] = ALL_SUGGESTION_FIELDS,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> list[FieldSuggestion]:
    detail_view = await _load_suggestion_context(
        session=session,
        resource_id=resource_id,
        licensed_sources=licensed_sources,
    )

    return await suggest_missing_field_values(
        resource_id=resource_id, detail_view=detail_view, fields=fields
    )
