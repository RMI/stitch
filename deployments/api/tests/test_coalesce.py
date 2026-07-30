"""Unit tests for the pure per-field coalescer.

Covers the default priority chain (rmi > wm > ccr > gem > llm, including the CCR
source ranking) and the per-(record, field) tiering: overridden records outrank
non-overridden ones for a field, so a source added after a reorder sorts last;
per-field isolation; same-source records ranked individually; and
backward-compatible default behaviour when no overrides are supplied.
"""

from stitch.api.coalesce import SOURCE_PRIORITY, coalesce_og_field_resource
from stitch.ogsi.model import (
    CCRSource,
    GemSource,
    LLMSource,
    RMISource,
    WoodMacSource,
)

from tests.utils import make_source_record

_RECORD = make_source_record()


def _gem(**kw):
    return GemSource(source_record=_RECORD, **kw)


def _wm(**kw):
    return WoodMacSource(source_record=_RECORD, **kw)


def _rmi(**kw):
    return RMISource(source_record=_RECORD, **kw)


def _ccr(**kw):
    return CCRSource(source_record=_RECORD, **kw)


def _llm(**kw):
    return LLMSource(source_record=_RECORD, **kw)


def test_defaults_pick_highest_priority_source_per_field():
    # No overrides -> rmi(1) > wm(2) > gem(4): rmi wins where present.
    sources = [
        _gem(id=2, name="GEM Name", country="USA", basin="Alpha"),
        _wm(id=3, name="WM Name", country="CAN", basin="Beta"),
        _rmi(id=1, name="RMI Name", country="MEX"),
    ]
    view, prov = coalesce_og_field_resource(sources)

    assert view.name == "RMI Name"  # rmi has top default priority
    assert view.basin == "Beta"  # rmi has no basin -> wm(2) wins over gem(4)
    assert prov["name"][1] == "rmi"
    assert prov["basin"][1] == "wm"


def test_override_flips_one_field_only():
    sources = [
        _gem(id=2, name="GEM Name", country="USA", basin="Alpha"),
        _wm(id=3, name="WM Name", country="CAN", basin="Beta"),
    ]
    # Pin gem(#2) first for basin only (gem is below wm by default); name keeps
    # the default (wm) winner.
    overrides = {"basin": {2: 0, 3: 1}}
    view, prov = coalesce_og_field_resource(sources, field_overrides=overrides)

    assert view.basin == "Alpha"
    assert prov["basin"][1] == "gem"
    assert view.name == "WM Name"
    assert prov["name"][1] == "wm"


def test_newly_added_source_sorts_last_despite_best_default():
    # gem + wm pinned for basin; rmi (best DEFAULT priority) has a basin value but
    # NO override -> it must sort last, so the pinned gem stays the winner.
    sources = [
        _gem(id=2, name="GEM", country="USA", basin="Alpha"),
        _wm(id=3, name="WM", country="CAN", basin="Beta"),
        _rmi(id=1, name="RMI", country="MEX", basin="Gamma"),
    ]
    overrides = {"basin": {2: 0, 3: 1}}
    view, prov = coalesce_og_field_resource(sources, field_overrides=overrides)

    assert view.basin == "Alpha"
    assert prov["basin"][1] == "gem"


def test_same_source_records_ranked_individually():
    # Two gem records; pin the second one for basin -> it wins over the first.
    sources = [
        _gem(id=1, name="GEM A", country="USA", basin="First"),
        _gem(id=2, name="GEM B", country="CAN", basin="Second"),
    ]
    overrides = {"basin": {2: 0}}
    view, prov = coalesce_og_field_resource(sources, field_overrides=overrides)

    assert view.basin == "Second"
    assert prov["basin"][1] == "gem"
    assert prov["basin"][2] == 2  # winning record id


def test_none_and_empty_overrides_match_default_order():
    sources = [
        _gem(id=2, name="GEM", country="USA", basin="Alpha"),
        _wm(id=3, name="WM", country="CAN", basin="Beta"),
        _llm(id=4, name="LLM", country="GBR"),
    ]
    baseline = coalesce_og_field_resource(sources, SOURCE_PRIORITY)
    with_none = coalesce_og_field_resource(sources, field_overrides=None)
    with_empty = coalesce_og_field_resource(sources, field_overrides={})

    assert with_none[0].model_dump() == baseline[0].model_dump()
    assert with_empty[0].model_dump() == baseline[0].model_dump()


def test_ccr_outranks_llm():
    # ccr (3) outranks llm (5): ccr's value wins the contested field.
    view, prov = coalesce_og_field_resource(
        [
            _llm(id=1, name="from-llm", country=None),
            _ccr(id=2, name="from-ccr", country=None),
        ]
    )

    assert view.name == "from-ccr"
    assert prov["name"] is not None
    assert prov["name"][1] == "ccr"


def test_wm_outranks_ccr():
    # wm (2) outranks ccr (3): wm's value wins the contested field.
    view, prov = coalesce_og_field_resource(
        [
            _ccr(id=1, name="from-ccr", country=None),
            _wm(id=2, name="from-wm", country=None),
        ]
    )

    assert view.name == "from-wm"
    assert prov["name"] is not None
    assert prov["name"][1] == "wm"


def test_wm_outranks_gem():
    # wm (2) outranks gem (4): wm's value wins the contested field.
    view, prov = coalesce_og_field_resource(
        [
            _gem(id=1, name="from-gem", country=None),
            _wm(id=2, name="from-wm", country=None),
        ]
    )

    assert view.name == "from-wm"
    assert prov["name"] is not None
    assert prov["name"][1] == "wm"
