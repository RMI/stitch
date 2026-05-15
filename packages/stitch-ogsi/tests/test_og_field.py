"""Smoke tests for stitch-ogsi compositional patterns.

These tests verify that the domain-specific models compose correctly
on top of stitch-models generics.  They also serve as usage examples.
"""

from __future__ import annotations
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from stitch.ogsi.model import (
    GemSource,
    OGFieldDetailView,
    OGFieldResource,
    OGFieldSource,
    SourceRecord,
    WoodMacSource,
)
from stitch.ogsi.model.og_field import OilGasFieldBase


# ---------------------------------------------------------------------------
# Discriminated union
# ---------------------------------------------------------------------------

_source_adapter = TypeAdapter(OGFieldSource)


class TestOGFieldSourceDiscriminator:
    """OGFieldSource routes JSON to the correct Source subclass."""

    def test_gem_source_from_json(self):
        obj = _source_adapter.validate_json(
            '{"source": "gem", "name": "Test Field", "country": "USA", "source_record": {"observed_at": "2026-01-01T00:00:00Z", "producer": "test", "payload": {"kind": "fixture"}}}'
        )
        assert isinstance(obj, GemSource)
        assert obj.source == "gem"
        assert obj.name == "Test Field"

    def test_wm_source_from_json(self):
        obj = _source_adapter.validate_json(
            '{"source": "wm", "name": "Test Field", "country": "NOR", "source_record": {"observed_at": "2026-01-01T00:00:00Z", "producer": "test", "payload": {"kind": "fixture"}}}'
        )
        assert isinstance(obj, WoodMacSource)
        assert obj.source == "wm"

    def test_invalid_source_key_rejected(self):
        with pytest.raises(ValidationError):
            _source_adapter.validate_json(
                '{"source": "unknown", "name": "X", "country": "USA"}'
            )

    def test_source_record_round_trips_on_source_variants(self):
        obj = _source_adapter.validate_python(
            {
                "source": "gem",
                "name": "Test Field",
                "country": "USA",
                "source_record": {
                    "observed_at": "2026-01-01T00:00:00Z",
                    "producer": "stitch-seed/0.1.0",
                    "payload": {"kind": "seed_faker", "source": {"name": "Test Field"}},
                },
            }
        )
        assert isinstance(obj, GemSource)
        assert obj.source_record == SourceRecord(
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            producer="stitch-seed/0.1.0",
            payload={"kind": "seed_faker", "source": {"name": "Test Field"}},
        )


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


class TestOGFieldDetailView:
    def test_source_view_validation_accepts_omitted_source_record(self):
        detail = OGFieldDetailView.model_validate(
            {
                "id": 1,
                "data": OilGasFieldBase(name="Alpha", country="USA").model_dump(),
                "provenance": {},
                "source_data": [
                    {"source": "gem", "name": "Alpha", "country": "USA"}
                ],
            }
        )

        assert len(detail.source_data) == 1
        assert detail.source_data[0].source == "gem"
        assert detail.source_data[0].source_record is None
