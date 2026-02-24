"""Minimal test doubles and fixtures for stitch-models."""

from __future__ import annotations

from typing import Literal, Mapping
from uuid import UUID

import pytest

from stitch.models import (
    ConstituentProvenance,
    Resource,
    ResourceBase,
    SourceBase,
    SourcePayload,
    SourceRef,
)
# ---------------------------------------------------------------------------
# Source doubles — each specializes to exactly one id type, matching the
# design intent that a given source uses only int, str, or UUID.
# ---------------------------------------------------------------------------

class FooSource(SourceBase[int, Literal["foo"]]):
    value: float


class BarSource(SourceBase[str, Literal["bar"]]):
    label: str


class UuidSource(SourceBase[UUID, Literal["uuid_src"]]):
    pass


# ---------------------------------------------------------------------------
# Payload doubles
# ---------------------------------------------------------------------------

class FooPayload(SourcePayload):
    foos: Mapping[int, FooSource] = {}


class MultiPayload(SourcePayload):
    foos: Mapping[int, FooSource] = {}
    bars: Mapping[str, BarSource] = {}


class UuidPayload(SourcePayload):
    uuids: Mapping[UUID, UuidSource] = {}


# ---------------------------------------------------------------------------
# Resource doubles
# ---------------------------------------------------------------------------

class FooResource(Resource[FooPayload, ConstituentProvenance]):
    pass


class MultiResource(Resource[MultiPayload, ConstituentProvenance]):
    pass


class ExtendedResourceBase(ResourceBase):
    extra: str


# ---------------------------------------------------------------------------
# ORM-like doubles (plain objects with attributes, for from_attributes tests)
# ---------------------------------------------------------------------------

class FooSourceORM:
    def __init__(self, id: int, source: str, value: float):
        self.id = id
        self.source = source
        self.value = value


class BarSourceORM:
    def __init__(self, id: str, source: str, label: str):
        self.id = id
        self.source = source
        self.label = label


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def foo_source():
    return FooSource(id=1, source="foo", value=3.14)


@pytest.fixture
def bar_source():
    return BarSource(id="abc", source="bar", label="test")


@pytest.fixture
def foo_payload(foo_source):
    return FooPayload(foos={1: foo_source})


@pytest.fixture
def foo_ref():
    return SourceRef(source="foo", id=1)


@pytest.fixture
def foo_provenance(foo_ref):
    return ConstituentProvenance(id=1, source_refs=[foo_ref])


@pytest.fixture
def foo_resource(foo_payload, foo_provenance):
    return FooResource(
        id=1,
        name="Test",
        source_data=foo_payload,
        provenance=[foo_provenance],
    )
