"""Factory functions for creating test data.

Provides factory functions that return both Pydantic models and dictionaries
for use in tests and HTTP client requests.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel
from stitch.ogsi.model import GemSource, OGSISrcKey, WoodMacSource

from .factories import ResourceFactory
from stitch.api.entities import Resource

T = TypeVar("T", bound=BaseModel)


def make_resource(
    *,
    fact: ResourceFactory,
    empty: bool = False,
    sources: list[tuple[OGSISrcKey, int]] = [],
):
    res = fact.build()
    if empty:
        res.source_data = []
        res.repointed_to = None
        res.id = None
        res.constituents = frozenset()
        res.provenance = {}

    return fact.build()


def make_create_resource(
    *, name: str | None = None, factory: ResourceFactory
) -> Resource:
    """Create a minimal Resource payload for creation tests."""
    src = [
        GemSource(name="fake_gem_source", country=None),
        WoodMacSource(name=None, country="USA"),
    ]
    model = factory.build()
    model.id = None
    return model


def make_empty_resource(
    *,
    name: str | None = None,
    factory: ResourceFactory,
    sources: list[tuple[OGSISrcKey, int]] = [],
) -> Resource:
    """Alias for make_create_resource() kept for readability."""
    res = factory.build()
    res.source_data = []
    res.repointed_to = None
    res.id = None
    res.constituents = frozenset()
    res.provenance = {}
    return make_create_resource(name=name, factory=factory)
