"""Coalescing priority tests for the CCR source.

CCR must rank between ``wm`` and ``gem``:
    rmi (1) > wm (2) > ccr (3) > gem (4) > llm (5)
so a higher-priority source's value wins a contested field.
"""

from __future__ import annotations

from datetime import UTC, datetime

from stitch.api.coalesce import coalesce_og_field_resource
from stitch.ogsi.model import (
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


def test_wm_outranks_gem():
    coalesced, provenance = coalesce_og_field_resource(
        [
            GemSource(id=1, name="from-gem", country=None, source_record=_record()),
            WoodMacSource(id=2, name="from-wm", country=None, source_record=_record()),
        ]
    )

    assert coalesced.name == "from-wm"
    assert provenance["name"] is not None
    assert provenance["name"][1] == "wm"
