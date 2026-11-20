from __future__ import annotations
from typing import Literal, get_args

from collections.abc import Collection
from sqlalchemy.ext.asyncio import AsyncSession
from stitch.api.db import og_field_resource_actions
from stitch.api.db.utils import resource_to_detail_view
from stitch.ogsi.model import OGFieldDetailView, OGSISrcKey
from stitch.core.llm import suggest_missing_field_values, FieldSuggestion

AllowedSuggestionField = Literal[
    "name",
    "name_local",
    "country",
    "basin",
    "region",
    "state_province",
    "reservoir_formation",
    "discovery_year",
    "fid_year",
    "production_start_year",
    "location_type",
    "field_status",
    "primary_hydrocarbon_group",
    "production_conventionality",
]


ALL_SUGGESTION_FIELDS: tuple[AllowedSuggestionField, ...] = get_args(
    AllowedSuggestionField
)


class OGFieldSuggestable(OGFieldDetailView):
    @property
    def suggestable_fields(self) -> tuple[AllowedSuggestionField, ...]:
        return ALL_SUGGESTION_FIELDS


async def _load_suggestion_context(
    *,
    session: AsyncSession,
    resource_id: int,
    licensed_sources: Collection[OGSISrcKey] | None = None,
) -> OGFieldSuggestable:
    resource = await og_field_resource_actions.get_resolved(
        session=session, id=resource_id, licensed_sources=licensed_sources
    )
    dv = resource_to_detail_view(resource)
    return OGFieldSuggestable(**dv.model_dump())


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
