"""Coalescing priority tests for the OGSI sources.

The coalescing ladder is:
    rmi (1) > wm (2) > ccr (3) > bc (4) > alb (5) > gem (6) > llm (7)
so a higher-priority source's value wins a contested field.
"""

from __future__ import annotations

from datetime import UTC, datetime

from stitch.api.coalesce import coalesce_og_field_resource
from stitch.ogsi.model import (
    ALBSource,
    BCSource,
    CCRSource,
    GemSource,
    LLMSource,
    SourceRecord,
    WoodMacSource,
)


def _record() -> SourceRecord:
    return SourceRecord(
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        producer="test",
        payload={"kind": "fixture"},
    )


def test_ccr_outranks_llm():
    coalesced, provenance = coalesce_og_field_resource(
        [
            LLMSource(id=1, name="from-llm", country=None, source_record=_record()),
            CCRSource(id=2, name="from-ccr", country=None, source_record=_record()),
        ]
    )

    assert coalesced.name == "from-ccr"
    assert provenance["name"] is not None
    assert provenance["name"][1] == "ccr"


def test_wm_outranks_ccr():
    coalesced, provenance = coalesce_og_field_resource(
        [
            CCRSource(id=1, name="from-ccr", country=None, source_record=_record()),
            WoodMacSource(id=2, name="from-wm", country=None, source_record=_record()),
        ]
    )

    assert coalesced.name == "from-wm"
    assert provenance["name"] is not None
    assert provenance["name"][1] == "wm"


def test_ccr_outranks_bc():
    coalesced, provenance = coalesce_og_field_resource(
        [
            BCSource(id=1, name="from-bc", country=None, source_record=_record()),
            CCRSource(id=2, name="from-ccr", country=None, source_record=_record()),
        ]
    )

    assert coalesced.name == "from-ccr"
    assert provenance["name"] is not None
    assert provenance["name"][1] == "ccr"


def test_bc_outranks_alb():
    coalesced, provenance = coalesce_og_field_resource(
        [
            ALBSource(id=1, name="from-alb", country=None, source_record=_record()),
            BCSource(id=2, name="from-bc", country=None, source_record=_record()),
        ]
    )

    assert coalesced.name == "from-bc"
    assert provenance["name"] is not None
    assert provenance["name"][1] == "bc"


def test_alb_outranks_gem():
    coalesced, provenance = coalesce_og_field_resource(
        [
            GemSource(id=1, name="from-gem", country=None, source_record=_record()),
            ALBSource(id=2, name="from-alb", country=None, source_record=_record()),
        ]
    )

    assert coalesced.name == "from-alb"
    assert provenance["name"] is not None
    assert provenance["name"][1] == "alb"


def test_gem_outranks_llm():
    coalesced, provenance = coalesce_og_field_resource(
        [
            LLMSource(id=1, name="from-llm", country=None, source_record=_record()),
            GemSource(id=2, name="from-gem", country=None, source_record=_record()),
        ]
    )

    assert coalesced.name == "from-gem"
    assert provenance["name"] is not None
    assert provenance["name"][1] == "gem"
