"""Tests for stitch.api.permissions.licensed_sources."""

import logging

from stitch.auth import TokenClaims

from stitch.api.permissions import licensed_sources


def _claims(*permissions: str) -> TokenClaims:
    return TokenClaims(sub="test|user", permissions=frozenset(permissions))


def test_empty_permissions_returns_empty_frozenset():
    assert licensed_sources(_claims()) == frozenset()


def test_single_valid_source():
    assert licensed_sources(_claims("resource:read:licensed:rmi")) == frozenset({"rmi"})


def test_multiple_valid_sources_deduped():
    claims = _claims(
        "resource:read:licensed:rmi",
        "resource:read:licensed:gem",
        "resource:read:licensed:rmi",
    )
    assert licensed_sources(claims) == frozenset({"rmi", "gem"})


def test_malformed_permission_strings_ignored():
    claims = _claims(
        "no-prefix",
        "resource:read:licensed:",  # empty source segment
        "resource:read:licensed:rmi:extra",  # trailing segment is not a valid source
    )
    assert licensed_sources(claims) == frozenset()


def test_unknown_source_value_ignored_with_debug_log(caplog):
    with caplog.at_level(logging.DEBUG, logger="stitch.api.permissions"):
        result = licensed_sources(_claims("resource:read:licensed:bogus"))
    assert result == frozenset()
    assert any("bogus" in rec.message for rec in caplog.records)


def test_mixed_valid_and_unknown_only_keeps_valid():
    claims = _claims(
        "resource:read:licensed:rmi",
        "resource:read:licensed:bogus",
        "resource:read:licensed:wm",
    )
    assert licensed_sources(claims) == frozenset({"rmi", "wm"})


def test_non_licensed_prefixes_ignored():
    claims = _claims(
        "resource:write:licensed:rmi",
        "admin",
        "resource:read:licensed:gem",
    )
    assert licensed_sources(claims) == frozenset({"gem"})
