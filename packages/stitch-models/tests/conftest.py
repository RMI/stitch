"""Minimal test doubles and fixtures for stitch-models."""

from __future__ import annotations

from typing import Literal, Mapping
from uuid import UUID, uuid4

from pydantic import Field
import pytest

from stitch.models import (
    Resource,
    Source,
    SourcePayload,
)

# ---------------------------------------------------------------------------
# Source doubles — each specializes to exactly one id type, matching the
# design intent that a given source uses only int, str, or UUID.
# ---------------------------------------------------------------------------


class FooSource(Source[int, Literal["foo"]]):
    source: Literal["foo"] = "foo"
    value: float


class BarSource(Source[UUID, Literal["bar"]]):
    source: Literal["bar"] = "bar"
    label: str


class UuidSource(Source[UUID, Literal["uuid_src"]]):
    source: Literal["uuid_src"] = "uuid_src"


# ---------------------------------------------------------------------------
# Payload doubles
# ---------------------------------------------------------------------------


class FooPayload(SourcePayload):
    foos: Mapping[int, FooSource] = Field(default_factory=dict)


class MultiPayload(SourcePayload):
    foos: Mapping[int, FooSource] = Field(default_factory=dict)
    bars: Mapping[str, BarSource] = Field(default_factory=dict)


class UuidPayload(SourcePayload):
    uuids: Mapping[UUID, UuidSource] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Resource doubles
# ---------------------------------------------------------------------------


class EmptyPayload(SourcePayload):
    pass


class FooResource(Resource[int, FooPayload]):
    pass


class MultiResource(Resource[int, MultiPayload]):
    pass


class ExtendedResource(Resource[int, EmptyPayload]):
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
    def __init__(self, id: UUID, source: str, label: str):
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
    return BarSource(id=uuid4(), label="test")


@pytest.fixture
def foo_payload(foo_source):
    return FooPayload(foos={1: foo_source})


@pytest.fixture
def foo_resource(foo_payload):
    return FooResource(id=1, source_data=foo_payload)
