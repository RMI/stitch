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
    OGFieldResource,
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


# ---------------------------------------------------------------------------
# Resource (multiple-inheritance mixin)
# ---------------------------------------------------------------------------


class TestOGFieldResource:
    """OGFieldResource combines OilAndGasFieldBase + Resource fields."""

    def test_has_both_base_class_fields(self, og_payload: Sequence[OGFieldSource]):
        resource = OGFieldResource(
            id=1,
            name="Merged Field",
            country="USA",
            source_data=og_payload,
            location_type="Onshore",
        )
        # OilAndGasFieldBase fields
        assert resource.name == "Merged Field"
        assert resource.location_type == "Onshore"
        # Resource fields
        assert resource.id == 1
        assert resource.source_data == og_payload
        assert resource.repointed_to is None
        assert resource.constituents == frozenset()

    def test_self_reference_rejected(self, og_payload: Sequence[OGFieldSource]):
        with pytest.raises(ValidationError, match="constituent of itself"):
            OGFieldResource(
                id=1,
                name="Bad",
                country="USA",
                source_data=og_payload,
                constituents=[1],
            )
