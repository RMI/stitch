"""Category B: Validation & rejection tests for stitch-models.

These tests verify that bad objects and shapes are rejected with the
expected Pydantic error types and locations.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from tests.conftest import (
    BarSource,
    FooPayload,
    FooResource,
    FooSource,
    MultiPayload,
    UuidSource,
)


def assert_has_error(errors: list[dict], *, type: str, loc: tuple) -> None:
    assert any(
        e["type"] == type and e["loc"] == loc for e in errors
    ), f"Expected {type} at {loc}, got: {[e['type'] + ' @ ' + str(e['loc']) for e in errors]}"


# ---------------------------------------------------------------------------
# Literal-parameterized `source` field rejects non-matching values
# ---------------------------------------------------------------------------


class TestSourceLiteralDiscrimination:
    def test_rejects_wrong_literal_via_dict(self):
        with pytest.raises(ValidationError) as exc_info:
            FooSource.model_validate({"id": 1, "source": "wrong", "value": 3.14})
        assert_has_error(exc_info.value.errors(), type="literal_error", loc=("source",))

    def test_rejects_wrong_literal_via_json(self):
        payload = json.dumps({"id": 1, "source": "wrong", "value": 3.14})
        with pytest.raises(ValidationError) as exc_info:
            FooSource.model_validate_json(payload)
        assert_has_error(exc_info.value.errors(), type="literal_error", loc=("source",))


# ---------------------------------------------------------------------------
# TId type parameter creates per-source id enforcement
# ---------------------------------------------------------------------------


class TestParameterizedIdTypeEnforcement:
    def test_int_id_rejects_non_numeric_string_via_json(self):
        payload = json.dumps({"id": "not_a_number", "source": "foo", "value": 3.14})
        with pytest.raises(ValidationError) as exc_info:
            FooSource.model_validate_json(payload)
        assert_has_error(exc_info.value.errors(), type="int_parsing", loc=("id",))

    def test_str_id_rejects_int_via_json(self):
        payload = json.dumps({"id": 123, "source": "bar", "label": "test"})
        with pytest.raises(ValidationError) as exc_info:
            BarSource.model_validate_json(payload)
        assert_has_error(exc_info.value.errors(), type="string_type", loc=("id",))

    def test_uuid_id_rejects_malformed_string(self):
        payload = json.dumps({"id": "not-a-uuid", "source": "uuid_src"})
        with pytest.raises(ValidationError) as exc_info:
            UuidSource.model_validate_json(payload)
        assert_has_error(exc_info.value.errors(), type="uuid_parsing", loc=("id",))


# ---------------------------------------------------------------------------
# Mapping[TId, TSrc] enforces both key and value types
# ---------------------------------------------------------------------------


class TestMappingTypeEnforcement:
    def test_rejects_non_coercible_key_via_json(self):
        payload = json.dumps(
            {"foos": {"abc": {"id": 1, "source": "foo", "value": 3.14}}}
        )
        with pytest.raises(ValidationError) as exc_info:
            FooPayload.model_validate_json(payload)
        assert_has_error(
            exc_info.value.errors(),
            type="int_parsing",
            loc=("foos", "abc", "[key]"),
        )

    def test_rejects_wrong_source_type_in_value(self):
        bar = BarSource(id="abc", source="bar", label="test")
        with pytest.raises(ValidationError) as exc_info:
            FooPayload(foos={1: bar})  # type: ignore[arg-type]
        errors = exc_info.value.errors()
        error_types = {e["type"] for e in errors}
        assert error_types & {"int_parsing", "literal_error", "missing"}

    def test_rejects_wrong_literal_in_nested_json(self):
        payload = json.dumps(
            {
                "foos": {"1": {"id": 1, "source": "bar", "value": 3.14}},
                "bars": {},
            }
        )
        with pytest.raises(ValidationError) as exc_info:
            MultiPayload.model_validate_json(payload)
        assert_has_error(
            exc_info.value.errors(),
            type="literal_error",
            loc=("foos", "1", "source"),
        )


# ---------------------------------------------------------------------------
# Resource required fields define the API surface
# ---------------------------------------------------------------------------


class TestResourceRequiredFields:
    def test_rejects_empty_json(self):
        with pytest.raises(ValidationError) as exc_info:
            FooResource.model_validate_json("{}")
        errors = exc_info.value.errors()
        missing_locs = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert missing_locs >= {"id", "source_data", "provenance"}

    def test_rejects_null_id_via_json(self):
        payload = json.dumps(
            {
                "id": None,
                "source_data": {"foos": {}},
                "provenance": [],
            }
        )
        with pytest.raises(ValidationError) as exc_info:
            FooResource.model_validate_json(payload)
        assert_has_error(exc_info.value.errors(), type="int_type", loc=("id",))


# ---------------------------------------------------------------------------
# NamedTuples serialize as arrays; Pydantic enforces exact arity
# ---------------------------------------------------------------------------


class TestNamedTupleArityEnforcement:
    def test_provenance_rejects_short_array(self):
        payload = json.dumps(
            {
                "id": 1,
                "source_data": {"foos": {}},
                "provenance": [[1]],
            }
        )
        with pytest.raises(ValidationError) as exc_info:
            FooResource.model_validate_json(payload)
        assert_has_error(
            exc_info.value.errors(),
            type="missing_argument",
            loc=("provenance", 0, "source_refs"),
        )

    def test_source_ref_rejects_extra_element(self):
        payload = json.dumps(
            {
                "id": 1,
                "source_data": {"foos": {}},
                "provenance": [[1, [["foo", 1, "extra"]]]],
            }
        )
        with pytest.raises(ValidationError) as exc_info:
            FooResource.model_validate_json(payload)
        assert_has_error(
            exc_info.value.errors(),
            type="unexpected_positional_argument",
            loc=("provenance", 0, 1, 0, 2),
        )


# ---------------------------------------------------------------------------
# Coercion leniency contracts (surprisingly permissive behaviors)
# ---------------------------------------------------------------------------


class TestCoercionLeniencyContracts:
    def test_provenance_accepts_object_format_in_json(self):
        """NamedTuples accept both array AND object format in JSON
        despite serializing only as arrays."""
        payload = json.dumps(
            {
                "id": 1,
                "source_data": {"foos": {}},
                "provenance": [{"id": 1, "source_refs": [["foo", 1]]}],
            }
        )
        resource = FooResource.model_validate_json(payload)
        assert resource.provenance[0].id == 1

    def test_float_coerces_to_int_id_via_json(self):
        """Lossless float->int coercion works (JS interop)."""
        payload = json.dumps({"id": 3.0, "source": "foo", "value": 1.0})
        source = FooSource.model_validate_json(payload)
        assert source.id == 3
        assert isinstance(source.id, int)
