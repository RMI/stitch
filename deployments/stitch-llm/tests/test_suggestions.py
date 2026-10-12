from __future__ import annotations

import json

import pytest

from stitch.llm.errors import ModelOutputError
from stitch.llm.suggestions import (
    build_field_suggestion_input,
    parse_field_suggestion_response,
    sanitize_and_validate_suggested_value,
)
from stitch.ogsi.model import GemSource, OGFieldDetailView, SourceRecord
from stitch.ogsi.model.og_field import OilGasFieldBase
from datetime import UTC, datetime


def make_detail_view(**data) -> OGFieldDetailView:
    return OGFieldDetailView(
        id=42,
        data=OilGasFieldBase(name="Alpha", country="USA", **data),
        provenance={},
        source_data=[
            GemSource(
                source="gem",
                name="Alpha",
                country="USA",
                source_record=SourceRecord(
                    observed_at=datetime(2026, 1, 1, tzinfo=UTC),
                    producer="test",
                    payload={"kind": "fixture"},
                ),
                **data,
            ),
        ],
    )


def test_parse_field_suggestion_response_parses_value_and_rationale() -> None:
    parsed = parse_field_suggestion_response(
        "VALUE: Permian Basin\nRATIONALE: Public sources identify the basin."
    )

    assert parsed.value == "Permian Basin"
    assert parsed.rationale == "Public sources identify the basin."


def test_parse_field_suggestion_response_requires_value_and_rationale_lines() -> None:
    with pytest.raises(ModelOutputError):
        parse_field_suggestion_response("VALUE: Permian Basin")


def test_parse_field_suggestion_response_rejects_extra_non_empty_lines() -> None:
    with pytest.raises(ModelOutputError):
        parse_field_suggestion_response(
            "VALUE: Permian Basin\nRATIONALE: Supported by sources.\nEXTRA: nope"
        )


def test_build_field_suggestion_input_excludes_source_record_from_prompt() -> None:
    detail_view = make_detail_view(basin=None)

    input_messages = build_field_suggestion_input(
        resource_id=42,
        field="basin",
        detail_view=detail_view,
    )

    payload = json.loads(input_messages[1]["content"])
    assert "source_record" not in payload["source_records"][0]


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
