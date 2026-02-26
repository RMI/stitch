"""Category D: serialization, JSON, and coercion tests."""

from __future__ import annotations

import json
from uuid import UUID

from stitch.models import SourceRef
from tests.conftest import (
    EmptyPayload,
    ExtendedResource,
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
        resource = MultiResource(
            id=1,
            source_data=payload,
            provenance={1: [SourceRef("foo", 1), SourceRef("bar", "abc")]},
        )
        dumped = resource.model_dump()
        restored = MultiResource.model_validate(dumped)
        assert restored == resource


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

        Provenance is a Mapping[int, Sequence[SourceRef]] where SourceRef
        serializes as arrays: {"1": [["foo", 1]]}.
        """
        handcrafted = json.dumps(
            {
                "id": 1,
                "repointed_to": None,
                "source_data": {
                    "foos": {"1": {"id": 1, "source": "foo", "value": 3.14}}
                },
                "provenance": {"1": [["foo", 1]]},
            }
        )

        restored = FooResource.model_validate_json(handcrafted)
        assert restored.id == 1
        assert restored.source_data.foos[1].value == 3.14
        assert restored.provenance[1][0] == SourceRef("foo", 1)


# ---------------------------------------------------------------------------
# model_validate from raw dict
# ---------------------------------------------------------------------------


class TestModelValidateFromDict:
    def test_resource_from_raw_dict(self):
        """Resource can be built from a plain nested dict (no model instances)."""
        raw = {
            "id": 1,
            "source_data": {
                "foos": {1: {"id": 1, "source": "foo", "value": 3.14}},
            },
            "provenance": {1: [SourceRef("foo", 1)]},
        }
        resource = FooResource.model_validate(raw)
        assert resource.id == 1
        assert resource.source_data.foos[1].value == 3.14


# ---------------------------------------------------------------------------
# repointed_to serialization
# ---------------------------------------------------------------------------


class TestRepointedToSerialization:
    def test_chain_round_trip(self):
        ep = EmptyPayload()
        a = ExtendedResource(id=1, source_data=ep, extra="a")
        b = ExtendedResource(id=2, source_data=ep, extra="b", repointed_to=a)
        c = ExtendedResource(id=3, source_data=ep, extra="c", repointed_to=b)

        # dict round-trip (2-level)
        dumped = b.model_dump()
        restored = ExtendedResource.model_validate(dumped)
        assert restored.repointed_to.extra == "a"

        # JSON round-trip (3-level)
        json_str = c.model_dump_json()
        restored = ExtendedResource.model_validate_json(json_str)
        assert restored.repointed_to.repointed_to.extra == "a"

    def test_subclass_json_round_trip(self):
        ep = EmptyPayload()
        inner = ExtendedResource(id=2, source_data=ep, extra="y")
        outer = ExtendedResource(id=1, source_data=ep, extra="x", repointed_to=inner)
        json_str = outer.model_dump_json()
        restored = ExtendedResource.model_validate_json(json_str)
        assert isinstance(restored.repointed_to, ExtendedResource)
        assert restored.repointed_to.extra == "y"

    def test_resource_with_repointed_to(self, foo_payload, foo_ref):
        inner = FooResource(
            id=2,
            source_data=foo_payload,
            provenance={2: [foo_ref]},
        )
        outer = FooResource(
            id=1,
            source_data=foo_payload,
            provenance={1: [foo_ref]},
            repointed_to=inner,
        )
        json_str = outer.model_dump_json()
        restored = FooResource.model_validate_json(json_str)
        assert restored.repointed_to.id == 2


# ---------------------------------------------------------------------------
# SourceRef serialization within provenance Mapping
# ---------------------------------------------------------------------------


class TestSourceRefSerializationInProvenance:
    def test_source_refs_serialize_as_tuples_and_arrays(self, foo_resource):
        """model_dump serializes SourceRefs as tuples; JSON uses arrays."""
        # model_dump → tuples in provenance values
        dumped = foo_resource.model_dump()
        refs = dumped["provenance"][1]
        assert isinstance(refs[0], tuple)
        assert refs[0] == ("foo", 1)

        # model_dump_json → arrays
        json_str = foo_resource.model_dump_json()
        parsed = json.loads(json_str)
        prov_json = parsed["provenance"]["1"]
        assert isinstance(prov_json[0], list)
        assert prov_json[0] == ["foo", 1]

    def test_multiple_provenance_entries(self, foo_source, bar_source):
        payload = MultiPayload(foos={1: foo_source}, bars={"abc": bar_source})
        resource = MultiResource(
            id=1,
            source_data=payload,
            provenance={
                1: [SourceRef("foo", 1)],
                2: [SourceRef("bar", "abc")],
            },
        )
        json_str = resource.model_dump_json()
        restored = MultiResource.model_validate_json(json_str)
        assert len(restored.provenance) == 2
        assert restored.provenance[1] == [SourceRef("foo", 1)]
        assert restored.provenance[2] == [SourceRef("bar", "abc")]


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
        src = FooSource(id=42, value=1.0)
        payload = FooPayload.model_validate({"foos": {42: src}})
        assert 42 in payload.foos

    def test_provenance_int_key_coerced_from_json_string(self):
        """Provenance Mapping keys coerce from JSON strings to int."""
        raw_json = json.dumps(
            {
                "id": 1,
                "source_data": {"foos": {}},
                "provenance": {"42": [["foo", 1]]},
            }
        )
        resource = FooResource.model_validate_json(raw_json)
        assert 42 in resource.provenance
