"""Fixtures for stitch-ogsi tests.

Each fixture constructs a realistic domain object, doubling as
documentation for how the models are intended to be used.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stitch.ogsi.model import (
    GemSource,
    WoodMacSource,
    OGSourcePayload,
    Owner,
    Operator,
)


@pytest.fixture
def gem_source() -> GemSource:
    """A GEM source record for a producing onshore oil field."""
    return GemSource(
        id=42,
        name="Permian Basin Field A",
        country="USA",
        latitude=31.95,
        longitude=-102.07,
        last_updated=datetime(2025, 6, 1, tzinfo=timezone.utc),
        location_type="Onshore",
        primary_hydrocarbon_group="Light Oil",
        production_conventionality="Unconventional",
        discovery_year=1986,
        production_start_year=1990,
        field_status="Producing",
        owners=[Owner(name="Acme Energy", stake=60.0)],
        operators=[Operator(name="Acme Energy", stake=100.0)],
    )


@pytest.fixture
def wm_source() -> WoodMacSource:
    """A WoodMac source record with minimal fields populated."""
    return WoodMacSource(
        id=99,
        name="North Sea Field B",
        country="GBR",
        location_type="Offshore",
        field_status="Producing",
    )


@pytest.fixture
def og_payload(gem_source: GemSource, wm_source: WoodMacSource) -> OGSourcePayload:
    return OGSourcePayload(gem=[gem_source], wm=[wm_source])
