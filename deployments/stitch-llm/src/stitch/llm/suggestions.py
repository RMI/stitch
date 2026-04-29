from __future__ import annotations

import json
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, ValidationError

from stitch.llm.errors import FieldAlreadyPopulatedError, ModelOutputError
from stitch.ogsi.model import OGFieldDetailView
from stitch.ogsi.model.og_field import OilGasFieldBase
from stitch.ogsi.model.types import (
    FieldStatus,
    LocationType,
    PrimaryHydrocarbonGroup,
    ProductionConventionality,
)

AllowedSuggestionField = Literal[
    "basin",
    "state_province",
    "discovery_year",
    "fid_year",
    "production_start_year",
    "location_type",
    "field_status",
    "primary_hydrocarbon_group",
    "production_conventionality",
]

STRING_FIELDS = frozenset({"basin", "state_province"})
YEAR_FIELDS = frozenset({"discovery_year", "fid_year", "production_start_year"})
ENUM_VALUES_BY_FIELD: dict[str, tuple[str, ...]] = {
    "location_type": get_args(LocationType),
    "field_status": get_args(FieldStatus),
    "primary_hydrocarbon_group": get_args(PrimaryHydrocarbonGroup),
    "production_conventionality": get_args(ProductionConventionality),
}


class ParsedFieldSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: AllowedSuggestionField
    value: Any
    citations: list["ParsedCitation"]


class ParsedCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str | None = None


def is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def ensure_field_is_missing(
    detail_view: OGFieldDetailView,
    field: AllowedSuggestionField,
) -> None:
    value = getattr(detail_view.data, field)
    if not is_missing_value(value):
        raise FieldAlreadyPopulatedError(f"Field `{field}` is already populated.")


def build_field_suggestion_input(
    *,
    resource_id: int,
    field: AllowedSuggestionField,
    detail_view: OGFieldDetailView,
) -> list[dict[str, str]]:
    field_info = OilGasFieldBase.model_fields[field]
    field_description = field_info.description or field.replace("_", " ")

    payload = {
        "task": "Infer one missing oil and gas field value from the provided Stitch record context.",
        "resource_id": resource_id,
        "field": field,
        "field_description": field_description,
        "instructions": [
            "Use only the provided coalesced_resource and source_records.",
            "Use web search to find publicly available evidence for the requested value.",
            "If you cannot support the value with one or more public citations, return null for value and an empty citations list.",
            "Return null when the value cannot be inferred from the provided data.",
            "Do not use outside knowledge.",
            "Do not return a value for any field except the requested field.",
        ],
        "coalesced_resource": detail_view.data.model_dump(mode="json"),
        "source_records": [
            source.model_dump(mode="json") for source in detail_view.source_data
        ],
    }

    return [
        {
            "role": "system",
            "content": (
                "You infer one missing oil and gas field value from Stitch data. "
                "Respond only with structured JSON matching the supplied schema."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, indent=2),
        },
    ]


def suggestion_response_schema(field: AllowedSuggestionField) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["field", "value", "citations"],
        "properties": {
            "field": {"type": "string", "enum": [field]},
            "value": _value_schema_for_field(field),
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["url", "title"],
                    "properties": {
                        "url": {"type": "string"},
                        "title": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    },
                },
            },
        },
    }


def _value_schema_for_field(field: AllowedSuggestionField) -> dict[str, Any]:
    if field in STRING_FIELDS:
        return {"anyOf": [{"type": "string"}, {"type": "null"}]}
    if field in YEAR_FIELDS:
        return {
            "anyOf": [
                {"type": "integer", "minimum": 1800, "maximum": 2100},
                {"type": "null"},
            ]
        }
    if field in ENUM_VALUES_BY_FIELD:
        return {
            "anyOf": [
                {"type": "string", "enum": list(ENUM_VALUES_BY_FIELD[field])},
                {"type": "null"},
            ]
        }
    raise AssertionError(f"Unsupported suggestion field: {field}")


def parse_field_suggestion_response(
    raw_output_text: str,
    *,
    requested_field: AllowedSuggestionField,
) -> ParsedFieldSuggestion:
    try:
        parsed = ParsedFieldSuggestion.model_validate(json.loads(raw_output_text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ModelOutputError("Model did not return valid suggestion JSON.") from exc

    if parsed.field != requested_field:
        raise ModelOutputError("Model returned a suggestion for the wrong field.")

    return parsed


def sanitize_and_validate_suggested_value(
    *,
    detail_data: OilGasFieldBase,
    field: AllowedSuggestionField,
    value: Any,
) -> Any:
    sanitized = _sanitize_value(field=field, value=value)
    candidate = detail_data.model_copy(update={field: sanitized})

    try:
        validated = OilGasFieldBase.model_validate(candidate.model_dump(mode="python"))
    except ValidationError as exc:
        raise ModelOutputError("Suggested value failed OGSI model validation.") from exc

    return getattr(validated, field)


def _sanitize_value(*, field: AllowedSuggestionField, value: Any) -> Any:
    if value is None:
        return None

    if field in STRING_FIELDS:
        if not isinstance(value, str):
            raise ModelOutputError(f"Suggested value for `{field}` must be a string.")
        cleaned = value.strip()
        return cleaned or None

    if field in YEAR_FIELDS:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned.isdigit():
                return int(cleaned)
        raise ModelOutputError(f"Suggested value for `{field}` must be an integer.")

    enum_values = ENUM_VALUES_BY_FIELD.get(field)
    if enum_values is not None:
        if not isinstance(value, str):
            raise ModelOutputError(f"Suggested value for `{field}` must be a string.")
        cleaned = value.strip()
        if not cleaned:
            return None
        by_casefold = {enum_value.casefold(): enum_value for enum_value in enum_values}
        try:
            return by_casefold[cleaned.casefold()]
        except KeyError as exc:
            raise ModelOutputError(
                f"Suggested value for `{field}` is not an allowed value."
            ) from exc

    raise AssertionError(f"Unsupported suggestion field: {field}")
