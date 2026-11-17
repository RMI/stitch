from collections.abc import Iterable
from pydantic import BaseModel
from typing import Literal, get_args, Protocol

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


class AnyDetailView[T: BaseModel, S: BaseModel](Protocol):
    @property
    def data(self) -> T: ...

    @property
    def source_data(self) -> Iterable[S]: ...
