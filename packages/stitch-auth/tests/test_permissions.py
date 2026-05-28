import logging

from stitch.auth.permissions import (
    ALL_PERMISSIONS,
    MERGE_CANDIDATE_CREATE,
    RESOURCE_READ,
    RESOURCE_WRITE,
    SERVICE_LLM_SUGGEST,
    SOURCE_READ_GEM,
    SOURCE_READ_PERMISSIONS,
    SOURCE_READ_RMI,
    SOURCE_WRITE,
    has_all_permissions,
    has_any_permission,
    missing_permissions,
    source_from_read_permission,
    source_read_permission,
    source_read_sources,
)


def test_all_permissions_contains_defined_route_permissions():
    assert {
        RESOURCE_READ,
        RESOURCE_WRITE,
        SOURCE_WRITE,
        MERGE_CANDIDATE_CREATE,
        SERVICE_LLM_SUGGEST,
        *SOURCE_READ_PERMISSIONS,
    }.issubset(ALL_PERMISSIONS)


def test_missing_permissions_uses_exact_matching():
    granted = {RESOURCE_READ, SOURCE_READ_RMI}

    assert missing_permissions(granted, [RESOURCE_READ, RESOURCE_WRITE]) == frozenset(
        {RESOURCE_WRITE}
    )
    assert missing_permissions(granted, ["resource"]) == frozenset({"resource"})


def test_has_all_permissions_uses_exact_matching():
    granted = {RESOURCE_READ, RESOURCE_WRITE}

    assert has_all_permissions(granted, [RESOURCE_READ, RESOURCE_WRITE])
    assert not has_all_permissions(granted, [RESOURCE_READ, "resource"])


def test_has_any_permission_uses_exact_matching():
    granted = {RESOURCE_READ}

    assert has_any_permission(granted, [SOURCE_READ_RMI, RESOURCE_READ])
    assert not has_any_permission(granted, [SOURCE_READ_RMI, "resource"])


def test_source_read_permission_formats_source():
    assert source_read_permission("gem") == SOURCE_READ_GEM


def test_source_from_read_permission_parses_known_source():
    assert source_from_read_permission(SOURCE_READ_RMI) == "rmi"


def test_source_from_read_permission_ignores_non_source_read_permission():
    assert source_from_read_permission(RESOURCE_READ) is None


def test_source_from_read_permission_ignores_malformed_source():
    assert source_from_read_permission("source:read:") is None
    assert source_from_read_permission("source:read:rmi:extra") is None


def test_source_from_read_permission_ignores_unknown_source(caplog):
    with caplog.at_level(logging.WARNING, logger="stitch.auth.permissions"):
        assert source_from_read_permission("source:read:bogus") is None

    assert any("source:read:bogus" in rec.message for rec in caplog.records)


def test_source_read_sources_dedupes_and_ignores_unknown():
    assert source_read_sources(
        [
            SOURCE_READ_RMI,
            SOURCE_READ_GEM,
            SOURCE_READ_RMI,
            "source:read:bogus",
            RESOURCE_READ,
        ]
    ) == frozenset({"rmi", "gem"})


def test_source_read_sources_accepts_explicit_valid_sources():
    assert source_read_sources(
        [SOURCE_READ_RMI, SOURCE_READ_GEM],
        valid_sources={"gem"},
    ) == frozenset({"gem"})
