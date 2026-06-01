"""Tests for stitch.api.permissions.licensed_sources."""

from stitch.auth import TokenClaims

from stitch.api.permissions import licensed_sources


def _claims(*permissions: str) -> TokenClaims:
    return TokenClaims(sub="test|user", permissions=frozenset(permissions))


def test_empty_permissions_returns_empty_frozenset():
    assert licensed_sources(_claims()) == frozenset()


def test_single_valid_source():
    assert licensed_sources(_claims("source:read:rmi")) == frozenset({"rmi"})


def test_multiple_valid_sources_deduped():
    claims = _claims(
        "source:read:rmi",
        "source:read:gem",
        "source:read:rmi",
    )
    assert licensed_sources(claims) == frozenset({"rmi", "gem"})


def test_malformed_permission_strings_ignored():
    claims = _claims(
        "no-prefix",
        "source:read:",  # empty source segment
        "source:read:rmi:extra",  # trailing segment is not a valid source
    )
    assert licensed_sources(claims) == frozenset()


def test_unknown_source_value_ignored():
    assert licensed_sources(_claims("source:read:bogus")) == frozenset()


def test_mixed_valid_and_unknown_only_keeps_valid():
    claims = _claims(
        "source:read:rmi",
        "source:read:bogus",
        "source:read:wm",
    )
    assert licensed_sources(claims) == frozenset({"rmi", "wm"})


def test_non_licensed_prefixes_ignored():
    claims = _claims(
        "source:write:rmi",
        "admin",
        "source:read:gem",
    )
    assert licensed_sources(claims) == frozenset({"gem"})
