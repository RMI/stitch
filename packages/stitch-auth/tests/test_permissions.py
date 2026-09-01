import logging

import pytest
from stitch.auth.errors import InsufficientPermissionsError
from stitch.auth.permissions import (
    ALL_PERMISSIONS,
    MERGE_CANDIDATE_CREATE,
    RESOURCE_READ,
    RESOURCE_WRITE,
    SERVICE_LLM_SUGGEST,
    SOURCE_READ_ALB,
    SOURCE_READ_BC,
    SOURCE_READ_CCR,
    SOURCE_READ_GEM,
    SOURCE_READ_PERMISSIONS,
    SOURCE_READ_RMI,
    SOURCE_WRITE,
    check_permissions,
    has_all_permissions,
    has_any_permission,
    missing_permissions,
    source_from_read_permission,
    source_read_permission,
    source_read_sources,
)

VALID_SOURCES = {"rmi", "gem"}


def test_all_permissions_contains_defined_route_permissions():
    assert {
        RESOURCE_READ,
        RESOURCE_WRITE,
        SOURCE_WRITE,
        MERGE_CANDIDATE_CREATE,
        SERVICE_LLM_SUGGEST,
        *SOURCE_READ_PERMISSIONS,
    }.issubset(ALL_PERMISSIONS)


def test_ccr_source_read_permission_is_registered():
    assert SOURCE_READ_CCR == "source:read:ccr"
    assert SOURCE_READ_CCR in SOURCE_READ_PERMISSIONS
    assert SOURCE_READ_CCR in ALL_PERMISSIONS


def test_source_read_sources_resolves_ccr():
    assert source_read_sources(
        [SOURCE_READ_CCR],
        valid_sources={"ccr"},
    ) == frozenset({"ccr"})


def test_bc_source_read_permission_is_registered():
    assert SOURCE_READ_BC == "source:read:bc"
    assert SOURCE_READ_BC in SOURCE_READ_PERMISSIONS
    assert SOURCE_READ_BC in ALL_PERMISSIONS


def test_source_read_sources_resolves_bc():
    assert source_read_sources(
        [SOURCE_READ_BC],
        valid_sources={"bc"},
    ) == frozenset({"bc"})


def test_alb_source_read_permission_is_registered():
    assert SOURCE_READ_ALB == "source:read:alb"
    assert SOURCE_READ_ALB in SOURCE_READ_PERMISSIONS
    assert SOURCE_READ_ALB in ALL_PERMISSIONS


def test_source_read_sources_resolves_alb():
    assert source_read_sources(
        [SOURCE_READ_ALB],
        valid_sources={"alb"},
    ) == frozenset({"alb"})


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
    assert (
        source_from_read_permission(SOURCE_READ_RMI, valid_sources=VALID_SOURCES)
        == "rmi"
    )


def test_source_from_read_permission_ignores_non_source_read_permission():
    assert (
        source_from_read_permission(RESOURCE_READ, valid_sources=VALID_SOURCES) is None
    )


def test_source_from_read_permission_ignores_malformed_source():
    assert (
        source_from_read_permission("source:read:", valid_sources=VALID_SOURCES) is None
    )
    assert (
        source_from_read_permission("source:read:rmi:", valid_sources=VALID_SOURCES)
        is None
    )
    assert (
        source_from_read_permission(
            "source:read:rmi:extra",
            valid_sources=VALID_SOURCES,
        )
        is None
    )


def test_source_from_read_permission_ignores_unknown_source(caplog):
    with caplog.at_level(logging.WARNING, logger="stitch.auth.permissions"):
        assert (
            source_from_read_permission(
                "source:read:bogus",
                valid_sources=VALID_SOURCES,
            )
            is None
        )

    assert any("source:read:bogus" in rec.message for rec in caplog.records)


def test_source_read_sources_dedupes_and_filters_with_explicit_valid_sources():
    assert source_read_sources(
        [
            SOURCE_READ_RMI,
            SOURCE_READ_GEM,
            SOURCE_READ_RMI,
            "source:read:bogus",
            RESOURCE_READ,
        ],
        valid_sources=VALID_SOURCES,
    ) == frozenset({"rmi", "gem"})


def test_source_read_sources_accepts_explicit_valid_sources():
    assert source_read_sources(
        [SOURCE_READ_RMI, SOURCE_READ_GEM],
        valid_sources={"gem"},
    ) == frozenset({"gem"})


def test_check_permissions_all_succeeds_when_all_required_are_granted():
    assert (
        check_permissions(
            {RESOURCE_READ, RESOURCE_WRITE},
            [RESOURCE_READ, RESOURCE_WRITE],
        )
        is None
    )


def test_check_permissions_all_raises_with_structured_error():
    with pytest.raises(InsufficientPermissionsError) as exc_info:
        check_permissions({RESOURCE_READ}, [RESOURCE_READ, RESOURCE_WRITE])

    exc = exc_info.value
    assert exc.granted == frozenset({RESOURCE_READ})
    assert exc.required == frozenset({RESOURCE_READ, RESOURCE_WRITE})
    assert exc.missing == frozenset({RESOURCE_WRITE})
    assert exc.detail == "Missing required permission(s): resource:write"
    assert str(exc) == exc.detail


def test_check_permissions_any_succeeds_when_any_candidate_is_granted():
    assert (
        check_permissions(
            {RESOURCE_READ},
            [SOURCE_READ_RMI, RESOURCE_READ],
            check="any",
        )
        is None
    )


def test_check_permissions_any_raises_when_no_candidates_are_granted():
    with pytest.raises(InsufficientPermissionsError) as exc_info:
        check_permissions(
            {SOURCE_READ_RMI},
            [RESOURCE_READ, RESOURCE_WRITE],
            check="any",
        )

    exc = exc_info.value
    assert exc.granted == frozenset({SOURCE_READ_RMI})
    assert exc.required == frozenset({RESOURCE_READ, RESOURCE_WRITE})
    assert exc.missing == frozenset({RESOURCE_READ, RESOURCE_WRITE})
    assert exc.detail == (
        "Missing required permission(s): resource:read, resource:write"
    )


@pytest.mark.parametrize("check", ["all", "any"])
def test_check_permissions_empty_required_succeeds(check):
    assert check_permissions({RESOURCE_READ}, [], check=check) is None


def test_check_permissions_invalid_check_raises_value_error():
    with pytest.raises(ValueError, match="unsupported permission check mode"):
        check_permissions({RESOURCE_READ}, [RESOURCE_READ], check="some")


def test_check_permissions_iterator_inputs_preserve_error_payloads():
    granted = iter([RESOURCE_READ])
    required = iter([RESOURCE_READ, RESOURCE_WRITE])

    with pytest.raises(InsufficientPermissionsError) as exc_info:
        check_permissions(granted, required)

    exc = exc_info.value
    assert exc.granted == frozenset({RESOURCE_READ})
    assert exc.required == frozenset({RESOURCE_READ, RESOURCE_WRITE})
    assert exc.missing == frozenset({RESOURCE_WRITE})


def test_check_permissions_raising_exc_handler_gets_structured_error():
    seen: list[InsufficientPermissionsError] = []

    def raise_forbidden(exc: InsufficientPermissionsError):
        seen.append(exc)
        raise RuntimeError("forbidden")

    with pytest.raises(RuntimeError, match="forbidden"):
        check_permissions(
            {RESOURCE_READ},
            [RESOURCE_WRITE],
            exc_handler=raise_forbidden,
        )

    assert len(seen) == 1
    assert seen[0].missing == frozenset({RESOURCE_WRITE})


def test_check_permissions_returning_exc_handler_still_raises_original_error():
    seen: list[InsufficientPermissionsError] = []

    def returns_unexpectedly(exc: InsufficientPermissionsError):
        seen.append(exc)

    with pytest.raises(InsufficientPermissionsError) as exc_info:
        check_permissions(
            {RESOURCE_READ},
            [RESOURCE_WRITE],
            exc_handler=returns_unexpectedly,
        )

    assert seen == [exc_info.value]
    assert exc_info.value.missing == frozenset({RESOURCE_WRITE})


def test_top_level_exports_permission_helper_and_error():
    from stitch.auth import (
        InsufficientPermissionsError as exported_error,
        check_permissions as exported_check_permissions,
    )

    assert exported_check_permissions is check_permissions
    assert exported_error is InsufficientPermissionsError
