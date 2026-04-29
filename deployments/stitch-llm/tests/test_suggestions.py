from __future__ import annotations

import pytest

from stitch.llm.errors import FieldAlreadyPopulatedError, ModelOutputError
from stitch.llm.suggestions import (
    ensure_field_is_missing,
    parse_field_suggestion_response,
    sanitize_and_validate_suggested_value,
    suggestion_response_schema,
)
from stitch.ogsi.model import GemSource, OGFieldDetailView
from stitch.ogsi.model.og_field import OilGasFieldBase


def make_detail_view(**data) -> OGFieldDetailView:
    return OGFieldDetailView(
        id=42,
        data=OilGasFieldBase(name="Alpha", country="USA", **data),
        provenance={},
        source_data=[
            GemSource(source="gem", name="Alpha", country="USA", **data),
        ],
    )


def test_ensure_field_is_missing_rejects_populated_field() -> None:
    detail_view = make_detail_view(basin="Permian Basin")

    with pytest.raises(FieldAlreadyPopulatedError):
        ensure_field_is_missing(detail_view, "basin")


def test_ensure_field_is_missing_accepts_blank_string() -> None:
    detail_view = make_detail_view(basin="  ")

    ensure_field_is_missing(detail_view, "basin")


def test_parse_field_suggestion_response_rejects_wrong_field() -> None:
    with pytest.raises(ModelOutputError):
        parse_field_suggestion_response(
            '{"field":"basin","value":"Permian Basin","citations":[]}',
            requested_field="state_province",
        )


def test_parse_field_suggestion_response_requires_citations_key() -> None:
    with pytest.raises(ModelOutputError):
        parse_field_suggestion_response(
            '{"field":"basin","value":"Permian Basin"}',
            requested_field="basin",
        )


def test_sanitize_and_validate_suggested_value_trims_strings() -> None:
    value = sanitize_and_validate_suggested_value(
        detail_data=OilGasFieldBase(name="Alpha", country="USA", basin=None),
        field="basin",
        value="  Permian Basin  ",
    )

    assert value == "Permian Basin"


def test_sanitize_and_validate_suggested_value_normalizes_enum_case() -> None:
    value = sanitize_and_validate_suggested_value(
        detail_data=OilGasFieldBase(name="Alpha", country="USA"),
        field="location_type",
        value=" offshore ",
    )

    assert value == "Offshore"


def test_sanitize_and_validate_suggested_value_rejects_invalid_year() -> None:
    with pytest.raises(ModelOutputError):
        sanitize_and_validate_suggested_value(
            detail_data=OilGasFieldBase(name="Alpha", country="USA"),
            field="discovery_year",
            value="unknown",
        )


def test_suggestion_response_schema_is_field_specific() -> None:
    schema = suggestion_response_schema("field_status")

    assert schema["properties"]["field"]["enum"] == ["field_status"]
    assert schema["properties"]["citations"]["type"] == "array"
    assert {
        "Producing",
        "Non-Producing",
        "Abandoned",
        "Planned",
    }.issubset(set(schema["properties"]["value"]["anyOf"][0]["enum"]))
