"""Resource & SourcePayload subclassing and validation tests."""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from tests.conftest import (
    BarSource,
    EmptyPayload,
    ExtendedResource,
    FooPayload,
    FooResource,
    FooSource,
    MultiPayload,
    UuidPayload,
    UuidSource,
)


def assert_has_error(errors: list[dict], *, type: str, loc: tuple) -> None:
    assert any(e["type"] == type and e["loc"] == loc for e in errors), (
        f"Expected {type} at {loc}, got: {[e['type'] + ' @ ' + str(e['loc']) for e in errors]}"
    )


# ---------------------------------------------------------------------------
# SourcePayload subclassing
# ---------------------------------------------------------------------------


class TestSourcePayloadSubclassing:
    def test_empty_defaults(self):
        payload = FooPayload()
        assert payload.foos == {}

    def test_single_source_payload(self, foo_source):
        payload = FooPayload(foos={1: foo_source})
        assert payload.foos[1].id == 1
        assert payload.foos[1].value == 3.14

    def test_multi_source_payload(self, foo_source, bar_source):
        payload = MultiPayload(
            foos={1: foo_source},
            bars={"abc": bar_source},
        )
        assert len(payload.foos) == 1
        assert len(payload.bars) == 1
        assert payload.bars["abc"].label == "test"

    def test_uuid_keyed_payload(self):
        uid = UUID("550e8400-e29b-41d4-a716-446655440000")
        src = UuidSource(id=uid)
        payload = UuidPayload(uuids={uid: src})
        assert payload.uuids[uid].id == uid


# ---------------------------------------------------------------------------
# Resource subclassing
# ---------------------------------------------------------------------------


class TestResourceSubclassing:
    def test_basic_instantiation(self, foo_payload):
        resource = FooResource(id=1, source_data=foo_payload)
        assert resource.id == 1
        assert resource.source_data.foos[1].value == 3.14

    def test_provenance_defaults_to_empty(self, foo_payload):
        resource = FooResource(id=1, source_data=foo_payload)
        assert resource.provenance == {}

    def test_repointed_to_defaults_to_none(self, foo_payload):
        resource = FooResource(id=1, source_data=foo_payload)
        assert resource.repointed_to is None

    def test_repointed_to_accepts_id(self, foo_payload):
        resource = FooResource(id=1, source_data=foo_payload, repointed_to=42)
        assert resource.repointed_to == 42

    def test_extra_fields_on_subclass(self):
        ep = EmptyPayload()
        resource = ExtendedResource(id=1, source_data=ep, extra="x")
        assert resource.extra == "x"


# ---------------------------------------------------------------------------
# Resource & Payload validation
# ---------------------------------------------------------------------------


class TestResourceValidation:
    def test_rejects_missing_source_data(self):
        with pytest.raises(ValidationError) as exc_info:
            FooResource.model_validate_json("{}")
        errors = exc_info.value.errors()
        missing_locs = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert "source_data" in missing_locs

    def test_rejects_wrong_source_in_payload(self):
        bar = BarSource(id="abc", label="test")
        with pytest.raises(ValidationError) as exc_info:
            FooPayload(foos={1: bar})  # type: ignore[arg-type]
        errors = exc_info.value.errors()
        error_types = {e["type"] for e in errors}
        assert error_types & {"int_parsing", "literal_error", "missing"}

    def test_rejects_non_coercible_mapping_key(self):
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
