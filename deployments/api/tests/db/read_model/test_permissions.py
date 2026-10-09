"""Exact permission-profile matching for the resource-state read model."""

from typing import get_args

import pytest

from stitch.api.db.read_model.permissions import (
    PERMISSION_MASKS,
    PROFILES,
    PUBLIC_SOURCES,
    RESTRICTED_SOURCES,
    read_model_mask,
    visible_sources_for_mask,
)
from stitch.ogsi.model.types import OGSISrcKey


def test_source_universe_is_exactly_public_plus_restricted():
    """Adding a source key must be a deliberate change to the profiles.

    A new key fails closed on its own (no grant that holds it equals a profile),
    but every caller holding it would silently lose the fast path. This test makes
    that gap visible: decide whether the new key is public or restricted.
    """
    assert frozenset(get_args(OGSISrcKey)) == PUBLIC_SOURCES | RESTRICTED_SOURCES


def test_public_and_restricted_are_disjoint():
    assert not PUBLIC_SOURCES & RESTRICTED_SOURCES


def test_profiles_are_the_four_documented_sets():
    assert PROFILES == {
        0: PUBLIC_SOURCES,
        1: PUBLIC_SOURCES | {"ccr"},
        2: PUBLIC_SOURCES | {"wm"},
        3: PUBLIC_SOURCES | {"wm", "ccr"},
    }
    assert PERMISSION_MASKS == (0, 1, 2, 3)


@pytest.mark.parametrize("mask", PERMISSION_MASKS)
def test_exact_profile_maps_to_its_mask(mask: int):
    assert read_model_mask(PROFILES[mask]) == mask


@pytest.mark.parametrize("mask", PERMISSION_MASKS)
def test_visible_sources_round_trip(mask: int):
    assert read_model_mask(visible_sources_for_mask(mask)) == mask


def test_matching_ignores_order_and_duplicates():
    sources = [*sorted(PUBLIC_SOURCES), "wm", "gem", "wm"]
    assert read_model_mask(sources) == 2


def test_unscoped_caller_uses_live():
    assert read_model_mask(None) is None


def test_empty_grant_uses_live():
    assert read_model_mask(frozenset()) is None


@pytest.mark.parametrize("missing", sorted(PUBLIC_SOURCES))
@pytest.mark.parametrize("restricted", [set(), {"wm"}, {"ccr"}, {"wm", "ccr"}])
def test_partial_public_grant_uses_live(missing: str, restricted: set[str]):
    """Never round a partial public grant to a nearby profile."""
    sources = (PUBLIC_SOURCES - {missing}) | restricted
    assert read_model_mask(sources) is None


@pytest.mark.parametrize("restricted", [{"wm"}, {"ccr"}, {"wm", "ccr"}])
def test_restricted_only_grant_uses_live(restricted: set[str]):
    assert read_model_mask(restricted) is None


@pytest.mark.parametrize("mask", PERMISSION_MASKS)
def test_unknown_extra_key_uses_live(mask: int):
    assert read_model_mask(PROFILES[mask] | {"not-a-source"}) is None  # type: ignore[operator]
