"""Resource & SourcePayload subclassing and validation tests."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from .conftest import (
    BarSource,
    EmptyPayload,
    ExtendedResource,
    FooPayload,
    FooResource,
    FooSource,
    MultiPayload,
    ResourceWithSrcUnion,
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

    def test_ingestion_defaults(self, foo_payload):
        """Ingestion context: id, repointed_to, and constituents all default."""
        resource = FooResource(source_data=foo_payload)
        assert resource.id is None
        assert resource.repointed_to is None
        assert resource.constituents == frozenset()

    def test_repointed_to_accepts_id(self, foo_payload):
        resource = FooResource(id=1, source_data=foo_payload, repointed_to=42)
        assert resource.repointed_to == 42

    def test_constituents_accepts_ids(self, foo_payload):
        resource = FooResource(id=1, source_data=foo_payload, constituents={2, 3})
        assert resource.constituents == frozenset({2, 3})
        assert isinstance(resource.constituents, frozenset)

    def test_repointed_to_and_constituents_independent(self, foo_payload):
        """Both can be set simultaneously — they are independent fields."""
        resource = FooResource(
            id=1, source_data=foo_payload, repointed_to=99, constituents={2, 3}
        )
        assert resource.repointed_to == 99
        assert resource.constituents == frozenset({2, 3})

    def test_extra_fields_on_subclass(self):
        ep = EmptyPayload()
        resource = ExtendedResource(id=1, source_data=ep, extra="x")
        assert resource.extra == "x"


class TestResourceSubclassingDiscriminatedUnion:
    def test_valid_source_data(self, foo_source: FooSource, bar_source: BarSource):
        data = [foo_source.model_dump(), bar_source.model_dump()]
        res = ResourceWithSrcUnion.model_validate(
            {"id": 1, "res_b": 4.5, "res_c": "hi", "source_data": data}
        )
        assert len(res.source_data) == 2
        assert res.res_c == "hi"
        assert res.res_b == 4.5

    def test_invalid_source_data_raises(self, foo_source: FooSource):
        bad_bar = BarSource(id=uuid4(), label="bbar").model_dump()
        bad_bar["label"] = 4

        with pytest.raises(ValidationError) as exc_info:
            res = ResourceWithSrcUnion.model_validate(
                {"id": 1, "res_b": 4.5, "res_c": "hi", "source_data": [bad_bar]}
            )

        errs = exc_info.value.errors()
        assert len(errs) == 1
        assert errs[0]["loc"] == ("source_data", 0, "bar", "label")


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
        bar = BarSource(id=uuid4(), label="test")
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

    def test_rejects_self_in_constituents(self, foo_payload):
        with pytest.raises(ValidationError, match="constituent of itself"):
            FooResource(id=1, source_data=foo_payload, constituents={1, 2})

    def test_rejects_self_repointed_to(self, foo_payload):
        with pytest.raises(ValidationError, match="repointed to itself"):
            FooResource(id=1, source_data=foo_payload, repointed_to=1)

    def test_constituents_coerces_list_from_json(self):
        payload = json.dumps(
            {
                "id": 1,
                "source_data": {"foos": {}},
                "constituents": [2, 3],
            }
        )
        resource = FooResource.model_validate_json(payload)
        assert resource.constituents == frozenset({2, 3})
        assert isinstance(resource.constituents, frozenset)
