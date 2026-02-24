"""Category A: subclassing & specialization tests."""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from stitch.models import ConstituentProvenance, ResourceBase, SourceRef
from tests.conftest import (
    BarSource,
    BarSourceORM,
    ExtendedResourceBase,
    FooPayload,
    FooResource,
    FooSource,
    FooSourceORM,
    MultiPayload,
    MultiResource,
    UuidPayload,
    UuidSource,
)


# ---------------------------------------------------------------------------
# SourceBase subclassing
# ---------------------------------------------------------------------------

class TestSourceBaseSubclassing:
    def test_instantiation_with_correct_types(self):
        src = FooSource(id=1, source="foo", value=3.14)
        assert src.id == 1
        assert src.source == "foo"
        assert src.value == 3.14

    def test_field_type_preservation(self):
        src = FooSource(id=1, source="foo", value=3.14)
        assert isinstance(src.id, int)
        assert isinstance(src.value, float)

    def test_wrong_literal_rejected(self):
        with pytest.raises(ValidationError):
            FooSource(id=1, source="wrong", value=3.14)

    def test_wrong_id_type_rejected(self):
        with pytest.raises(ValidationError):
            FooSource(id="not_a_number", source="foo", value=3.14)

    def test_numeric_string_coerced_to_int(self):
        src = FooSource(id="42", source="foo", value=1.0)
        assert src.id == 42
        assert isinstance(src.id, int)

    def test_string_id_subclass(self):
        src = BarSource(id="abc", source="bar", label="test")
        assert src.id == "abc"
        assert isinstance(src.id, str)

    def test_uuid_id_subclass(self):
        uid = UUID("550e8400-e29b-41d4-a716-446655440000")
        src = UuidSource(id=uid, source="uuid_src")
        assert src.id == uid
        assert isinstance(src.id, UUID)


# ---------------------------------------------------------------------------
# SourcePayload subclassing
# ---------------------------------------------------------------------------

class TestSourcePayloadSubclassing:
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

    def test_empty_defaults(self):
        payload = FooPayload()
        assert payload.foos == {}

    def test_uuid_keyed_payload(self):
        uid = UUID("550e8400-e29b-41d4-a716-446655440000")
        src = UuidSource(id=uid, source="uuid_src")
        payload = UuidPayload(uuids={uid: src})
        assert payload.uuids[uid].id == uid


# ---------------------------------------------------------------------------
# Resource specialization
# ---------------------------------------------------------------------------

class TestResourceSpecialization:
    def test_full_instantiation(self, foo_resource):
        assert foo_resource.id == 1
        assert foo_resource.name == "Test"
        assert len(foo_resource.provenance) == 1

    def test_inherits_resource_base_fields(self, foo_resource):
        assert hasattr(foo_resource, "name")
        assert hasattr(foo_resource, "country")
        assert hasattr(foo_resource, "repointed_to")
        assert foo_resource.country is None
        assert foo_resource.repointed_to is None

    def test_multi_source_resource(self, foo_source, bar_source):
        payload = MultiPayload(foos={1: foo_source}, bars={"abc": bar_source})
        prov = ConstituentProvenance(
            id=1,
            source_refs=[SourceRef(source="foo", id=1), SourceRef(source="bar", id="abc")],
        )
        resource = MultiResource(id=1, source_data=payload, provenance=[prov])
        assert len(resource.source_data.foos) == 1
        assert len(resource.source_data.bars) == 1


# ---------------------------------------------------------------------------
# from_attributes (ORM-like objects)
# ---------------------------------------------------------------------------

class TestFromAttributes:
    def test_foo_source_from_orm(self):
        orm = FooSourceORM(id=1, source="foo", value=3.14)
        src = FooSource.model_validate(orm, from_attributes=True)
        assert src.id == 1
        assert src.source == "foo"
        assert src.value == 3.14

    def test_bar_source_from_orm(self):
        orm = BarSourceORM(id="abc", source="bar", label="test")
        src = BarSource.model_validate(orm, from_attributes=True)
        assert src.id == "abc"
        assert src.label == "test"

    def test_config_inheritance(self):
        assert FooSource.model_config.get("from_attributes") is True
        assert BarSource.model_config.get("from_attributes") is True


# ---------------------------------------------------------------------------
# repointed_to Self resolution
# ---------------------------------------------------------------------------

class TestRepointedToSelf:
    def test_base_class_chain(self):
        inner = ResourceBase(name="inner")
        outer = ResourceBase(name="outer", repointed_to=inner)
        assert outer.repointed_to is not None
        assert outer.repointed_to.name == "inner"

    def test_self_resolves_to_subclass(self):
        inner = ExtendedResourceBase(extra="y")
        outer = ExtendedResourceBase(extra="x", repointed_to=inner)
        assert isinstance(outer.repointed_to, ExtendedResourceBase)
        assert outer.repointed_to.extra == "y"

    def test_three_level_deep_chain(self):
        a = ResourceBase(name="a")
        b = ResourceBase(name="b", repointed_to=a)
        c = ResourceBase(name="c", repointed_to=b)
        assert c.repointed_to.repointed_to.name == "a"

    def test_none_terminates(self):
        a = ResourceBase(name="a")
        assert a.repointed_to is None
