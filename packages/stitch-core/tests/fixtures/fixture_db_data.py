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
        "name": "Permian Basin Oil Field",
        "country": "USA",
        "latitude": 31.8457,
        "longitude": -102.3676,
        "created_by": "user",
    },
    "gem_minimal": {
        "created_by": "user",
    },
    "woodmac_full": {
        "name": "Ghawar Field",
        "country": "SAU",
        "latitude": 25.5,
        "longitude": 49.5,
        "created_by": "user",
    },
    "edge_case_no_location": {
        "name": "Unknown Location Field",
        "country": "IRQ",
        "latitude": None,
        "longitude": None,
        "created_by": "user",
    },
    "edge_case_no_operator": {
        "name": "Orphaned Field",
        "country": "VEN",
        "latitude": 10.5,
        "longitude": -66.9,
        "created_by": "user",
    },
    "edge_case_long_name": {
        "name": "The Extraordinarily Long Named Oil and Gas Extraction Field with Multiple Operators and Complex Ownership Structure in Remote Location",
        "country": "RUS",
        "latitude": 61.5240,
        "longitude": 105.3188,
        "created_by": "user",
    },
    "edge_case_special_chars": {
        "name": "Field with Spëcial Çharacters & Symbols (Тест)",
        "country": "KAZ",
        "latitude": 47.0,
        "longitude": 51.5,
        "created_by": "user",
    },
    "edge_case_extreme_coordinates": {
        "name": "Arctic Offshore Field",
        "country": "NOR",
        "latitude": 89.999999,
        "longitude": -179.999999,
        "created_by": "user",
    },
    "edge_case_zero_coordinates": {
        "name": "Null Island Field",
        "country": None,
        "latitude": 0.0,
        "longitude": 0.0,
        "created_by": "user",
    },
}

# Membership test data
MEMBERSHIP_DATA: dict[str, MembershipEntityData] = {
    "gem_active": {
        "resource_id": 0,
        "source": "gem",
        "source_pk": "GEM-2024-001",
    },
    "gem_inactive": {
        "resource_id": 0,
        "source": "gem",
        "source_pk": "GEM-2024-002",
    },
    "woodmac_numeric": {
        "resource_id": 0,
        "source": "woodmac",
        "source_pk": "12345",
    },
    "woodmac_alphanumeric": {
        "resource_id": 0,
        "source": "woodmac",
        "source_pk": "WM-2024-ABC",
    },
    "duplicate_source_different_resource": {
        "resource_id": 0,
        "source": "gem",
        "source_pk": "GEM-DUP-001",
    },
}

# Repointed resources (for merge/split testing in the future)
REPOINTED_RESOURCE_DATA = {
    "merged_child": {
        "source": "gem",
        "source_pk": "GEM-MERGED-CHILD",
        "repointed_to": 1,  # Will need to be set dynamically in tests
        "name": "Merged Child Field",
        "country": "USA",
    },
    "merged_parent": {
        "source": "woodmac",
        "source_pk": "99999",
        "name": "Parent Field (Post-Merge)",
        "country": "USA",
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
