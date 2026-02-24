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
    def test_instantiation_and_type_preservation(self):
        src = FooSource(id=1, source="foo", value=3.14)
        assert src.id == 1
        assert src.source == "foo"
        assert src.value == 3.14
        assert isinstance(src.id, int)
        assert isinstance(src.value, float)

    def test_id_type_specialization(self):
        # int id with coercion from numeric string
        foo = FooSource(id="42", source="foo", value=1.0)
        assert foo.id == 42
        assert isinstance(foo.id, int)

        # str id
        bar = BarSource(id="abc", source="bar", label="test")
        assert bar.id == "abc"
        assert isinstance(bar.id, str)

        # UUID id
        uid = UUID("550e8400-e29b-41d4-a716-446655440000")
        uuidsrc = UuidSource(id=uid, source="uuid_src")
        assert uuidsrc.id == uid
        assert isinstance(uuidsrc.id, UUID)

    def test_wrong_literal_rejected(self):
        with pytest.raises(ValidationError):
            FooSource(id=1, source="wrong", value=3.14)

    def test_wrong_id_type_rejected(self):
        with pytest.raises(ValidationError):
            FooSource(id="not_a_number", source="foo", value=3.14)


# ---------------------------------------------------------------------------
# SourcePayload subclassing
# ---------------------------------------------------------------------------


class TestSourcePayloadSubclassing:
    def test_single_source_payload(self, foo_source):
        # empty default
        empty = FooPayload()
        assert empty.foos == {}

        # populated
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
        # inherited optional fields default to None
        assert foo_resource.country is None
        assert foo_resource.repointed_to is None

    def test_multi_source_resource(self, foo_source, bar_source):
        payload = MultiPayload(foos={1: foo_source}, bars={"abc": bar_source})
        prov = ConstituentProvenance(
            id=1,
            source_refs=[
                SourceRef(source="foo", id=1),
                SourceRef(source="bar", id="abc"),
            ],
        )
        resource = MultiResource(id=1, source_data=payload, provenance=[prov])
        assert len(resource.source_data.foos) == 1
        assert len(resource.source_data.bars) == 1


# ---------------------------------------------------------------------------
# from_attributes (ORM-like objects)
# ---------------------------------------------------------------------------


class TestFromAttributes:
    def test_from_attributes(self):
        # config inheritance
        assert FooSource.model_config.get("from_attributes") is True
        assert BarSource.model_config.get("from_attributes") is True

        # FooSource from ORM
        foo_orm = FooSourceORM(id=1, source="foo", value=3.14)
        foo = FooSource.model_validate(foo_orm, from_attributes=True)
        assert foo.id == 1
        assert foo.source == "foo"
        assert foo.value == 3.14

        # BarSource from ORM
        bar_orm = BarSourceORM(id="abc", source="bar", label="test")
        bar = BarSource.model_validate(bar_orm, from_attributes=True)
        assert bar.id == "abc"
        assert bar.label == "test"


# ---------------------------------------------------------------------------
# repointed_to Self resolution
# ---------------------------------------------------------------------------


class TestRepointedToSelf:
    def test_chain_traversal(self):
        a = ResourceBase(name="a")
        b = ResourceBase(name="b", repointed_to=a)
        c = ResourceBase(name="c", repointed_to=b)

        # full traversal
        assert c.repointed_to.repointed_to.name == "a"
        assert c.repointed_to.name == "b"

        # innermost terminates with None
        assert a.repointed_to is None

    def test_self_resolves_to_subclass(self):
        inner = ExtendedResourceBase(extra="y")
        outer = ExtendedResourceBase(extra="x", repointed_to=inner)
        assert isinstance(outer.repointed_to, ExtendedResourceBase)
        assert outer.repointed_to.extra == "y"
