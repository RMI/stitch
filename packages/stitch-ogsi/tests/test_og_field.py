"""Smoke tests for stitch-ogsi compositional patterns.

These tests verify that the domain-specific models compose correctly
on top of stitch-models generics.  They also serve as usage examples.
"""

from __future__ import annotations
from collections.abc import Sequence

import pytest
from pydantic import TypeAdapter, ValidationError

from stitch.ogsi.model import (
    GemSource,
    GemSourceCreate,
    OGFieldResource,
    OGFieldResourceCreate,
    OGFieldSource,
    WoodMacSource,
)


# ---------------------------------------------------------------------------
# Discriminated union
# ---------------------------------------------------------------------------

_source_adapter = TypeAdapter(OGFieldSource)


class TestOGFieldSourceDiscriminator:
    """OGFieldSource routes JSON to the correct Source subclass."""

    def test_gem_source_from_json(self):
        obj = _source_adapter.validate_json(
            '{"source": "gem", "name": "Test Field", "country": "USA"}'
        )
        assert isinstance(obj, GemSource)
        assert obj.source == "gem"
        assert obj.name == "Test Field"

    def test_wm_source_from_json(self):
        obj = _source_adapter.validate_json(
            '{"source": "wm", "name": "Test Field", "country": "NOR"}'
        )
        assert isinstance(obj, WoodMacSource)
        assert obj.source == "wm"

    def test_invalid_source_key_rejected(self):
        with pytest.raises(ValidationError):
            _source_adapter.validate_json(
                '{"source": "unknown", "name": "X", "country": "USA"}'
            )


class TestOGFieldSourceCreate:
    def test_source_record_is_required_on_create(self):
        with pytest.raises(ValidationError):
            GemSourceCreate.model_validate(
                {"source": "gem", "name": "Test Field", "country": "USA"}
            )

    def test_source_record_payload_accepts_json_compatible_values(self):
        source = GemSourceCreate.model_validate(
            {
                "source": "gem",
                "name": "Test Field",
                "country": "USA",
                "source_record": {
                    "kind": "seed_static",
                    "record_id": None,
                    "run_id": "run-1",
                    "observed_at": "2026-01-01T00:00:00Z",
                    "producer": "stitch-seed@0.1.0",
                    "payload": {
                        "a": ["b", 1, True, None],
                        "nested": {"c": "d"},
                    },
                },
            }
        )

        assert source.source_record.producer == "stitch-seed@0.1.0"
        assert source.source_record.payload["nested"] == {"c": "d"}

    def test_resource_create_requires_new_sources_with_source_record(self):
        resource = OGFieldResourceCreate.model_validate(
            {
                "id": None,
                "source_data": [
                    {
                        "source": "gem",
                        "name": "Test Field",
                        "country": "USA",
                        "source_record": {
                            "kind": "seed_static",
                            "record_id": None,
                            "run_id": "run-1",
                            "observed_at": "2026-01-01T00:00:00Z",
                            "producer": "stitch-seed@0.1.0",
                            "payload": {"source": "gem", "name": "Test Field"},
                        },
                    },
                ],
            }
        )

        assert len(resource.source_data) == 1
        assert resource.source_data[0].source == "gem"


# ---------------------------------------------------------------------------
# Resource (multiple-inheritance mixin)
# ---------------------------------------------------------------------------


class TestOGFieldResource:
    """OGFieldResource combines OilAndGasFieldBase + Resource fields."""

    def test_has_both_base_class_fields(self, og_payload: Sequence[OGFieldSource]):
        resource = OGFieldResource(
            id=1,
            source_data=og_payload,
        )
        # Resource fields
        assert resource.id == 1
        assert resource.source_data == og_payload
        assert resource.repointed_to is None
        assert resource.constituents == frozenset()

    def test_self_reference_rejected(self, og_payload: Sequence[OGFieldSource]):
        with pytest.raises(ValidationError, match="constituent of itself"):
            OGFieldResource(
                id=1,
                source_data=og_payload,
                constituents=[1],
            )
