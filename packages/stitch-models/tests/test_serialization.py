"""Category D: serialization, JSON, and coercion tests."""

from __future__ import annotations

import json
from uuid import UUID

from stitch.models import ConstituentProvenance, ResourceBase, SourceRef
from tests.conftest import (
    ExtendedResourceBase,
    FooPayload,
    FooResource,
    FooSource,
    MultiPayload,
    MultiResource,
    UuidPayload,
)

TEST_UUID = UUID("550e8400-e29b-41d4-a716-446655440000")


# ---------------------------------------------------------------------------
# model_dump → model_validate round-trip
# ---------------------------------------------------------------------------


class TestModelDumpValidateRoundTrip:
    def test_foo_resource_round_trip(self, foo_resource):
        dumped = foo_resource.model_dump()
        restored = FooResource.model_validate(dumped)
        assert restored == foo_resource

    def test_multi_resource_round_trip(self, foo_source, bar_source):
        payload = MultiPayload(foos={1: foo_source}, bars={"abc": bar_source})
        prov = ConstituentProvenance(
            id=1,
            source_refs=[SourceRef("foo", 1), SourceRef("bar", "abc")],
        )
        resource = MultiResource(id=1, source_data=payload, provenance=[prov])
        dumped = resource.model_dump()
        restored = MultiResource.model_validate(dumped)
        assert restored == resource

    def test_provenance_preservation(self, foo_resource):
        dumped = foo_resource.model_dump()
        restored = FooResource.model_validate(dumped)
        assert restored.provenance == foo_resource.provenance


# ---------------------------------------------------------------------------
# model_validate_json
# ---------------------------------------------------------------------------


class TestModelValidateJson:
    def test_from_model_dump_json(self, foo_resource):
        json_str = foo_resource.model_dump_json()
        restored = FooResource.model_validate_json(json_str)
        assert restored == foo_resource

    def test_from_handcrafted_json(self):
        """Validate that a hand-built JSON string parses correctly.

        NamedTuples serialize as arrays in JSON (not objects), so provenance
        and SourceRef appear as nested arrays: [[id, [[source, id], ...]]].
        """
        handcrafted = json.dumps(
            {
                "id": 1,
                "name": "Test",
                "country": None,
                "repointed_to": None,
                "source_data": {
                    "foos": {"1": {"id": 1, "source": "foo", "value": 3.14}}
                },
                "provenance": [[1, [["foo", 1]]]],
            }
        )

        restored = FooResource.model_validate_json(handcrafted)
        assert restored.id == 1
        assert restored.name == "Test"
        assert restored.source_data.foos[1].value == 3.14
        assert restored.provenance[0].id == 1
        assert restored.provenance[0].source_refs[0] == SourceRef("foo", 1)


# ---------------------------------------------------------------------------
# model_validate from raw dict
# ---------------------------------------------------------------------------


class TestModelValidateFromDict:
    def test_resource_from_raw_dict(self):
        """Resource can be built from a plain nested dict (no model instances)."""
        raw = {
            "id": 1,
            "name": "Test",
            "source_data": {
                "foos": {1: {"id": 1, "source": "foo", "value": 3.14}},
            },
            "provenance": [
                ConstituentProvenance(id=1, source_refs=[SourceRef("foo", 1)]),
            ],
        }
        resource = FooResource.model_validate(raw)
        assert resource.id == 1
        assert resource.source_data.foos[1].value == 3.14

    def test_provenance_from_nested_structures(self):
        """Provenance can be supplied as raw nested sequences."""
        # Discover what format model_dump uses for provenance, then feed it back
        ref = SourceRef("foo", 1)
        prov = ConstituentProvenance(id=1, source_refs=[ref])
        src = FooSource(id=1, source="foo", value=1.0)
        resource = FooResource(
            id=1,
            source_data=FooPayload(foos={1: src}),
            provenance=[prov],
        )
        dumped = resource.model_dump()
        # Validate from the raw dumped dict (provenance is whatever Pydantic serialized)
        restored = FooResource.model_validate(dumped)
        assert restored.provenance[0].id == 1


# ---------------------------------------------------------------------------
# repointed_to serialization
# ---------------------------------------------------------------------------


class TestRepointedToSerialization:
    def test_base_class_round_trip(self):
        inner = ResourceBase(name="inner")
        outer = ResourceBase(name="outer", repointed_to=inner)
        dumped = outer.model_dump()
        restored = ResourceBase.model_validate(dumped)
        assert restored.repointed_to.name == "inner"

    def test_subclass_json_round_trip(self):
        inner = ExtendedResourceBase(extra="y")
        outer = ExtendedResourceBase(extra="x", repointed_to=inner)
        json_str = outer.model_dump_json()
        restored = ExtendedResourceBase.model_validate_json(json_str)
        assert isinstance(restored.repointed_to, ExtendedResourceBase)
        assert restored.repointed_to.extra == "y"

    def test_deep_chain_json_round_trip(self):
        a = ResourceBase(name="a")
        b = ResourceBase(name="b", repointed_to=a)
        c = ResourceBase(name="c", repointed_to=b)
        json_str = c.model_dump_json()
        restored = ResourceBase.model_validate_json(json_str)
        assert restored.repointed_to.repointed_to.name == "a"

    def test_resource_with_repointed_to(self, foo_payload, foo_provenance):
        inner = FooResource(
            id=2,
            source_data=foo_payload,
            provenance=[foo_provenance],
            name="inner",
        )
        outer = FooResource(
            id=1,
            source_data=foo_payload,
            provenance=[foo_provenance],
            name="outer",
            repointed_to=inner,
        )
        json_str = outer.model_dump_json()
        restored = FooResource.model_validate_json(json_str)
        assert restored.repointed_to.name == "inner"
        assert restored.repointed_to.id == 2


# ---------------------------------------------------------------------------
# NamedTuple sequence serialization
# ---------------------------------------------------------------------------


class TestNamedTupleSequenceSerialization:
    def test_provenance_dumps_as_tuple(self, foo_resource):
        """model_dump serializes NamedTuples as tuples, not dicts."""
        dumped = foo_resource.model_dump()
        prov_dumped = dumped["provenance"][0]
        assert isinstance(prov_dumped, tuple)
        assert prov_dumped[0] == 1  # ConstituentProvenance.id

    def test_source_ref_dumps_as_nested_tuple(self, foo_resource):
        """Nested SourceRef within provenance also serializes as a tuple."""
        dumped = foo_resource.model_dump()
        ref_dumped = dumped["provenance"][0][1][0]  # first source_ref
        assert isinstance(ref_dumped, tuple)
        assert ref_dumped == ("foo", 1)

    def test_json_output_is_arrays(self, foo_resource):
        """JSON serialization uses nested arrays for NamedTuples."""
        json_str = foo_resource.model_dump_json()
        parsed = json.loads(json_str)
        prov_json = parsed["provenance"][0]
        assert isinstance(prov_json, list)
        assert prov_json[0] == 1  # ConstituentProvenance.id
        ref_json = prov_json[1][0]
        assert isinstance(ref_json, list)
        assert ref_json == ["foo", 1]

    def test_multiple_provenance_entries(self, foo_source, bar_source):
        payload = MultiPayload(foos={1: foo_source}, bars={"abc": bar_source})
        provs = [
            ConstituentProvenance(id=1, source_refs=[SourceRef("foo", 1)]),
            ConstituentProvenance(id=2, source_refs=[SourceRef("bar", "abc")]),
        ]
        resource = MultiResource(id=1, source_data=payload, provenance=provs)
        json_str = resource.model_dump_json()
        restored = MultiResource.model_validate_json(json_str)
        assert len(restored.provenance) == 2
        assert restored.provenance[0].id == 1
        assert restored.provenance[1].id == 2


# ---------------------------------------------------------------------------
# JSON key coercion
# ---------------------------------------------------------------------------


class TestJsonKeyCoercion:
    def test_int_key_coerced_from_json_string(self):
        """JSON object keys are always strings; Pydantic must coerce '42' → 42."""
        raw_json = '{"foos": {"42": {"id": 42, "source": "foo", "value": 1.0}}}'
        payload = FooPayload.model_validate_json(raw_json)
        assert 42 in payload.foos

    def test_str_key_stays_str(self):
        raw_json = '{"bars": {"abc": {"id": "abc", "source": "bar", "label": "test"}}}'
        payload = MultiPayload.model_validate_json(raw_json)
        assert "abc" in payload.bars

    def test_uuid_key_coerced_from_json_string(self):
        uid_str = str(TEST_UUID)
        raw_json = (
            f'{{"uuids": {{"{uid_str}": {{"id": "{uid_str}", "source": "uuid_src"}}}}}}'
        )
        payload = UuidPayload.model_validate_json(raw_json)
        assert TEST_UUID in payload.uuids

    def test_int_key_from_dict_stays_int(self):
        src = FooSource(id=42, source="foo", value=1.0)
        payload = FooPayload.model_validate({"foos": {42: src}})
        assert 42 in payload.foos
