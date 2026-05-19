from __future__ import annotations

from typing import Any, Literal, get_args

from pydantic import ValidationError

from stitch.llm.errors import FieldAlreadyPopulatedError, ModelOutputError
from stitch.ogsi.model import OGFieldDetailView, OG_FIELD_SOURCE_VIEW_ADAPTER
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


class ParsedFieldSuggestion:
    def __init__(self, *, value: Any, rationale: str) -> None:
        self.value = value
        self.rationale = rationale


def is_string_suggestion_field(field: AllowedSuggestionField) -> bool:
    return field in STRING_FIELDS


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
            "If you cannot support the value with one or more public citations, return VALUE: null.",
            "Return VALUE: null when the value cannot be inferred from the provided data.",
            "Do not use outside knowledge.",
            "Do not return a value for any field except the requested field.",
        ],
        "coalesced_resource": detail_view.data.model_dump(mode="json"),
        "source_records": _build_prompt_source_records(detail_view),
    }

    return [
        {
            "role": "system",
            "content": (
                "You infer one missing oil and gas field value from Stitch data. "
                "Use public web search evidence when needed. "
                "Respond using exactly two lines in this format:\n"
                "VALUE: <value or null>\n"
                "RATIONALE: <one short sentence>\n"
                "Do not output JSON. Do not add any extra lines."
            ),
        },
        {
            "role": "user",
            "content": _serialize_prompt_payload(payload),
        },
    ]


def _build_prompt_source_records(
    detail_view: OGFieldDetailView,
) -> list[dict[str, Any]]:
    return [
        OG_FIELD_SOURCE_VIEW_ADAPTER.validate_python(source).model_dump(mode="json")
        for source in detail_view.source_data
    ]


def _serialize_prompt_payload(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_field_suggestion_response(
    raw_output_text: str,
) -> ParsedFieldSuggestion:
    non_empty_lines = [
        line.strip() for line in raw_output_text.splitlines() if line.strip()
    ]
    if len(non_empty_lines) != 2:
        raise ModelOutputError(
            "Model did not return the expected two-line VALUE/RATIONALE format."
        )

    value_prefix = "VALUE:"
    rationale_prefix = "RATIONALE:"
    value_raw, rationale_raw = non_empty_lines

    if not value_raw.startswith(value_prefix) or not rationale_raw.startswith(
        rationale_prefix
    ):
        raise ModelOutputError(
            "Model did not return the expected VALUE/RATIONALE format."
        )

    value_line = value_raw.partition(":")[2].strip()
    rationale_line = rationale_raw.partition(":")[2].strip()

    value: Any
    if value_line.lower() == "null":
        value = None
    else:
        value = value_line

    if not rationale_line:
        raise ModelOutputError("Model did not return a rationale.")

    return ParsedFieldSuggestion(value=value, rationale=rationale_line)


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
