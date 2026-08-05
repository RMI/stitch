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
    ALBSource,
    BCSource,
    CCRSource,
    GemSource,
    OGFieldDetailView,
    OGFieldResource,
    OGFieldSource,
    SourceRecord,
    WoodMacSource,
)
from stitch.ogsi.model import OilGasOperator, OilGasOwner
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

    def test_ccr_source_from_json(self):
        obj = _source_adapter.validate_json(
            '{"source": "ccr", "name": "Test Field", "country": "USA", "source_record": {"observed_at": "2026-01-01T00:00:00Z", "producer": "test", "payload": {"kind": "fixture"}}}'
        )
        assert isinstance(obj, CCRSource)
        assert obj.source == "ccr"
        assert obj.name == "Test Field"

    def test_bc_source_from_json(self):
        obj = _source_adapter.validate_json(
            '{"source": "bc", "name": "Test Field", "country": "CAN", "source_record": {"observed_at": "2026-01-01T00:00:00Z", "producer": "test", "payload": {"kind": "fixture"}}}'
        )
        assert isinstance(obj, BCSource)
        assert obj.source == "bc"
        assert obj.name == "Test Field"

    def test_alb_source_from_json(self):
        obj = _source_adapter.validate_json(
            '{"source": "alb", "name": "Test Field", "country": "CAN", "source_record": {"observed_at": "2026-01-01T00:00:00Z", "producer": "test", "payload": {"kind": "fixture"}}}'
        )
        assert isinstance(obj, ALBSource)
        assert obj.source == "alb"
        assert obj.name == "Test Field"

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
# Ownership
# ---------------------------------------------------------------------------


class TestOwnershipStake:
    """`stake` is optional: providers often name a party without a percentage."""

    @pytest.mark.parametrize("model", [OilGasOwner, OilGasOperator])
    def test_stake_defaults_to_none_when_omitted(self, model):
        party = model(name="Acme Energy")
        assert party.stake is None

    @pytest.mark.parametrize("model", [OilGasOwner, OilGasOperator])
    def test_explicit_null_stake_accepted(self, model):
        party = model.model_validate({"name": "Acme Energy", "stake": None})
        assert party.stake is None

    @pytest.mark.parametrize("model", [OilGasOwner, OilGasOperator])
    def test_stated_stake_is_parsed(self, model):
        party = model(name="Acme Energy", stake=53.14)
        assert party.stake == 53.14

    @pytest.mark.parametrize("model", [OilGasOwner, OilGasOperator])
    def test_out_of_range_stake_still_rejected(self, model):
        with pytest.raises(ValidationError):
            model(name="Acme Energy", stake=150)

    def test_field_round_trips_mixed_stated_and_null_stakes(self):
        field = OilGasFieldBase(
            name="Alpha",
            country="USA",
            owners=[
                OilGasOwner(name="Sval Energi AS", stake=20.0),
                OilGasOwner(name="Petoro AS"),
            ],
            operators=[OilGasOperator(name="Equinor Energy AS")],
        )

        dumped = field.model_dump()
        assert dumped["owners"] == [
            {"name": "Sval Energi AS", "stake": 20.0},
            {"name": "Petoro AS", "stake": None},
        ]
        assert dumped["operators"] == [{"name": "Equinor Energy AS", "stake": None}]
        assert OilGasFieldBase.model_validate(dumped) == field


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
                "source_data": [{"source": "gem", "name": "Alpha", "country": "USA"}],
            }
        )

        assert len(detail.source_data) == 1
        assert detail.source_data[0].source == "gem"
        assert detail.source_data[0].source_record is None
