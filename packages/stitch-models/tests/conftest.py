"""Minimal test doubles and fixtures for stitch-models."""

from __future__ import annotations

from typing import Literal, Mapping
from uuid import UUID

import pytest

from stitch.models import (
    Resource,
    Source,
    SourcePayload,
    SourceRef,
)

# ---------------------------------------------------------------------------
# Source doubles — each specializes to exactly one id type, matching the
# design intent that a given source uses only int, str, or UUID.
# ---------------------------------------------------------------------------


class FooSource(Source[int, Literal["foo"]]):
    source: Literal["foo"] = "foo"
    value: float


class BarSource(Source[str, Literal["bar"]]):
    source: Literal["bar"] = "bar"
    label: str


class UuidSource(Source[UUID, Literal["uuid_src"]]):
    source: Literal["uuid_src"] = "uuid_src"


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


class EmptyPayload(SourcePayload):
    pass


class FooResource(Resource[FooPayload, int]):
    pass


class MultiResource(Resource[MultiPayload, int]):
    pass


class ExtendedResource(Resource[EmptyPayload, int]):
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
    return FooSource(id=1, value=3.14)


@pytest.fixture
def bar_source():
    return BarSource(id="abc", label="test")


@pytest.fixture
def foo_payload(foo_source):
    return FooPayload(foos={1: foo_source})


@pytest.fixture
def foo_ref():
    return SourceRef(source="foo", id=1)


@pytest.fixture
def foo_resource(foo_payload, foo_ref):
    return FooResource(
        id=1,
        source_data=foo_payload,
        provenance={1: [foo_ref]},
    )
