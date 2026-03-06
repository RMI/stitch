"""Source subclassing & validation tests."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from tests.conftest import (
    BarSource,
    BarSourceORM,
    FooSource,
    FooSourceORM,
    UuidSource,
)


def assert_has_error(errors: list[dict], *, type: str, loc: tuple) -> None:
    assert any(e["type"] == type and e["loc"] == loc for e in errors), (
        f"Expected {type} at {loc}, got: {[e['type'] + ' @ ' + str(e['loc']) for e in errors]}"
    )


# ---------------------------------------------------------------------------
# Subclassing
# ---------------------------------------------------------------------------


class TestSourceSubclassing:
    def test_instantiation_preserves_types(self):
        src = FooSource(id=1, value=3.14)
        assert src.id == 1
        assert src.source == "foo"
        assert src.value == 3.14
        assert isinstance(src.id, int)
        assert isinstance(src.value, float)

    def test_source_default_from_subclass(self):
        """Subclass-declared default means source need not be passed."""
        foo = FooSource(id=1, value=1.0)
        assert foo.source == "foo"

        bar = BarSource(id=uuid4(), label="test")
        assert bar.source == "bar"

    def test_id_type_specialization(self):
        # int id with coercion from numeric string
        foo = FooSource(id="42", value=1.0)
        assert foo.id == 42
        assert isinstance(foo.id, int)

        # UUID id
        uid = uuid4()
        bar = BarSource(id=uid, label="test")
        assert bar.id == uid
        assert isinstance(bar.id, UUID)

        # UUID id
        uid = UUID("550e8400-e29b-41d4-a716-446655440000")
        uuidsrc = UuidSource(id=uid)
        assert uuidsrc.id == uid
        assert isinstance(uuidsrc.id, UUID)

    def test_id_defaults_to_none(self):
        src = FooSource(value=1.0)
        assert src.id is None

    def test_from_attributes_config_inherited(self):
        assert FooSource.model_config.get("from_attributes") is True
        assert BarSource.model_config.get("from_attributes") is True

    def test_from_attributes_orm_object(self):
        foo_orm = FooSourceORM(id=1, source="foo", value=3.14)
        foo = FooSource.model_validate(foo_orm, from_attributes=True)
        assert foo.id == 1
        assert foo.source == "foo"
        assert foo.value == 3.14

        uid = uuid4()
        bar_orm = BarSourceORM(id=uid, source="bar", label="test")
        bar = BarSource.model_validate(bar_orm, from_attributes=True)
        assert bar.id == uid
        assert bar.label == "test"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestSourceValidation:
    def test_rejects_wrong_literal_via_dict(self):
        with pytest.raises(ValidationError) as exc_info:
            FooSource.model_validate({"id": 1, "source": "wrong", "value": 3.14})
        assert_has_error(exc_info.value.errors(), type="literal_error", loc=("source",))

    def test_rejects_wrong_literal_via_json(self):
        payload = json.dumps({"id": 1, "source": "wrong", "value": 3.14})
        with pytest.raises(ValidationError) as exc_info:
            FooSource.model_validate_json(payload)
        assert_has_error(exc_info.value.errors(), type="literal_error", loc=("source",))

    def test_int_id_rejects_non_numeric_string(self):
        payload = json.dumps({"id": "not_a_number", "source": "foo", "value": 3.14})
        with pytest.raises(ValidationError) as exc_info:
            FooSource.model_validate_json(payload)
        assert_has_error(exc_info.value.errors(), type="int_parsing", loc=("id",))

    def test_uuid_id_rejects_int_via_json(self):
        payload = json.dumps({"id": 123, "source": "bar", "label": "test"})
        with pytest.raises(ValidationError) as exc_info:
            BarSource.model_validate_json(payload)
        assert_has_error(exc_info.value.errors(), type="uuid_type", loc=("id",))

    def test_uuid_id_rejects_malformed_string(self):
        payload = json.dumps({"id": "not-a-uuid", "source": "uuid_src"})
        with pytest.raises(ValidationError) as exc_info:
            UuidSource.model_validate_json(payload)
        assert_has_error(exc_info.value.errors(), type="uuid_parsing", loc=("id",))

    def test_float_coerces_to_int_losslessly(self):
        """Lossless float->int coercion works (JS interop)."""
        payload = json.dumps({"id": 3.0, "source": "foo", "value": 1.0})
        source = FooSource.model_validate_json(payload)
        assert source.id == 3
        assert isinstance(source.id, int)
