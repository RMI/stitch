"""Test data constants for SQL adapter testing.

This module contains sample data for resources and memberships, including
various edge cases and realistic scenarios.
"""

from datetime import datetime, timezone

from stitch.core.resources.domain.entities import (
    ResourceEntityData,
    MembershipEntityData,
)

# Resource test data - various scenarios and edge cases
RESOURCE_DATA: dict[str, ResourceEntityData] = {
    "gem_full": {
        "dataset": "gem",
        "source_pk": "GEM-2024-001",
        "name": "Permian Basin Oil Field",
        "country_iso3": "USA",
        "operator": "ExxonMobil Corporation",
        "latitude": 31.8457,
        "longitude": -102.3676,
        # "created_by": "user",
    },
    "gem_minimal": {
        "dataset": "gem",
        "source_pk": "GEM-2024-002",
        # "created_by": "user",
    },
    "woodmac_full": {
        "dataset": "woodmac",
        "source_pk": "12345",
        "name": "Ghawar Field",
        "country_iso3": "SAU",
        "operator": "Saudi Aramco",
        "latitude": 25.5,
        "longitude": 49.5,
        # "created_by": "user",
    },
    "woodmac_numeric_pk": {
        "dataset": "woodmac",
        "source_pk": "987654321",
        "name": "North Sea Field",
        "country_iso3": "GBR",
        "operator": "BP plc",
        "latitude": 58.0,
        "longitude": 1.5,
        # "created_by": "user",
    },
    "edge_case_no_location": {
        "dataset": "gem",
        "source_pk": "GEM-NO-LOC-001",
        "name": "Unknown Location Field",
        "country_iso3": "IRQ",
        "operator": "Iraq National Oil Company",
        "latitude": None,
        "longitude": None,
        # "created_by": "user",
    },
    "edge_case_no_operator": {
        "dataset": "woodmac",
        "source_pk": "WM-2024-ABC",
        "name": "Orphaned Field",
        "country_iso3": "VEN",
        "operator": None,
        "latitude": 10.5,
        "longitude": -66.9,
        # "created_by": "user",
    },
    "edge_case_long_name": {
        "dataset": "gem",
        "source_pk": "GEM-LONG-NAME-001",
        "name": "The Extraordinarily Long Named Oil and Gas Extraction Field with Multiple Operators and Complex Ownership Structure in Remote Location",
        "country_iso3": "RUS",
        "operator": "Gazprom Neft",
        "latitude": 61.5240,
        "longitude": 105.3188,
        # "created_by": "user",
    },
    "edge_case_special_chars": {
        "dataset": "woodmac",
        "source_pk": "WM-SPEC-CHAR-001",
        "name": "Field with Spëcial Çharacters & Symbols (Тест)",
        "country_iso3": "KAZ",
        "operator": "КазМунайГаз",
        "latitude": 47.0,
        "longitude": 51.5,
        # "created_by": "user",
    },
    "edge_case_extreme_coordinates": {
        "dataset": "gem",
        "source_pk": "GEM-EXTREME-001",
        "name": "Arctic Offshore Field",
        "country_iso3": "NOR",
        "operator": "Equinor ASA",
        "latitude": 89.999999,
        "longitude": -179.999999,
        # "created_by": "user",
    },
    "edge_case_zero_coordinates": {
        "dataset": "woodmac",
        "source_pk": "555-ZERO",
        "name": "Null Island Field",
        "country_iso3": None,
        "operator": "Test Operator",
        "latitude": 0.0,
        "longitude": 0.0,
        # "created_by": "user",
    },
}

# Membership test data
MEMBERSHIP_DATA: dict[str, MembershipEntityData] = {
    "gem_active": {
        "resource_id": 0,
        "dataset": "gem",
        "source_pk": "GEM-2024-001",
    },
    "gem_inactive": {
        "resource_id": 0,
        "dataset": "gem",
        "source_pk": "GEM-2024-002",
    },
    "woodmac_numeric": {
        "resource_id": 0,
        "dataset": "woodmac",
        "source_pk": "12345",
    },
    "woodmac_alphanumeric": {
        "resource_id": 0,
        "dataset": "woodmac",
        "source_pk": "WM-2024-ABC",
    },
    "duplicate_source_different_resource": {
        "resource_id": 0,
        "dataset": "gem",
        "source_pk": "GEM-DUP-001",
    },
}

# Repointed resources (for merge/split testing in the future)
REPOINTED_RESOURCE_DATA = {
    "merged_child": {
        "dataset": "gem",
        "source_pk": "GEM-MERGED-CHILD",
        "repointed_id": 1,  # Will need to be set dynamically in tests
        "name": "Merged Child Field",
        "country_iso3": "USA",
    },
    "merged_parent": {
        "dataset": "woodmac",
        "source_pk": "99999",
        "name": "Parent Field (Post-Merge)",
        "country_iso3": "USA",
    },
}


def create_resource_with_timestamp(base_data: dict, **overrides) -> dict:
    """Create resource data with custom timestamp.

    Args:
        base_data: Base resource data from RESOURCE_DATA.
        **overrides: Fields to override or add.

    Returns:
        dict: Resource data with overrides applied.
    """
    data = base_data.copy()
    data.update(overrides)
    return data


def create_membership_with_timestamp(
    base_data: dict, ingested_at: datetime | None = None, **overrides
) -> dict:
    """Create membership data with custom timestamp.

    Args:
        base_data: Base membership data from MEMBERSHIP_DATA.
        ingested_at: Custom ingestion timestamp (defaults to now).
        **overrides: Fields to override or add.

    Returns:
        dict: Membership data with overrides applied.
    """
    data = base_data.copy()
    if ingested_at:
        data["ingested_at"] = ingested_at
    else:
        data["ingested_at"] = datetime.now(timezone.utc)
    data.update(overrides)
    return data
