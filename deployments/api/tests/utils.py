# pyright: reportAny=false
"""Factory functions for creating test data.

Provides factory functions that return both Pydantic models and dictionaries
for use in tests and HTTP client requests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel
from stitch.ogsi.model import (
    GemSource,
    GemSourceCreate,
    LLMSource,
    LLMSourceCreate,
    OGSISrcKey,
    OGFieldResourceCreate,
    RMISource,
    RMISourceCreate,
    WoodMacSource,
    WoodMacSourceCreate,
    OGFieldResource,
    OGFieldSource,
    OGFieldSourceCreate,
)

from .factories import OGFieldBaseFactory, ResourceFactory

T = TypeVar("T", bound=BaseModel)


def make_source_record(*, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "kind": "seed_static",
        "record_id": None,
        "run_id": "test-run-id",
        "observed_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
        "producer": "stitch-seed@test",
        "payload": payload or {"fixture": True},
    }


def make_source(
    fact: OGFieldBaseFactory,
    managed: bool = True,
    source: OGSISrcKey = "gem",
    **kwargs: Any,
) -> OGFieldSource:
    base = fact.build()
    id_ = fact.__random__.randint(1, 100) if managed else None
    src_str = f"{source.upper()} Source name"
    if id_ is not None:
        src_str += f" id {id_}"
    src_name: str | None = src_str if fact.__random__.random() >= 0.5 else None

    kwargs: dict[str, Any] = {
        **base.model_dump(),
        "id": id_,
        "name": src_name,
        **kwargs,
    }

    match source:
        case "llm":
            return LLMSource(**kwargs)
        case "rmi":
            return RMISource(**kwargs)
        case "wm":
            return WoodMacSource(**kwargs)
        case "gem":
            return GemSource(**kwargs)


def make_create_source(
    fact: OGFieldBaseFactory,
    source: OGSISrcKey = "gem",
    **kwargs: Any,
) -> OGFieldSourceCreate:
    base = fact.build()
    payload: dict[str, Any] = {
        **base.model_dump(),
        "id": None,
        **kwargs,
    }
    payload["source_record"] = make_source_record(payload=payload.copy())

    match source:
        case "llm":
            return LLMSourceCreate(source="llm", **payload)
        case "rmi":
            return RMISourceCreate(source="rmi", **payload)
        case "wm":
            return WoodMacSourceCreate(source="wm", **payload)
        case "gem":
            return GemSourceCreate(source="gem", **payload)


def make_resource(
    *,
    fact: ResourceFactory,
    base_fact: OGFieldBaseFactory,
    empty: bool = False,
    sources: list[tuple[OGSISrcKey, bool]] | None = None,
    **kwargs: Any,
):
    if sources is None:
        sources = []
    kw: dict[str, Any] = {
        "source_data": [
            make_source(base_fact, managed=mangd, source=sk) for sk, mangd in sources
        ],
        **kwargs,
    }
    if empty:
        kw["repointed_to"] = None
        kw["id"] = None
        kw["constituents"] = frozenset()
        kw["provenance"] = {}

    return fact.build(**kw)


def make_create_resource(
    *,
    name: str | None = None,
    base_factory: OGFieldBaseFactory,
    sources: list[OGSISrcKey] | None = None,
) -> OGFieldResourceCreate:
    """Create a minimal Resource payload for creation tests."""
    if sources is None:
        sources = ["gem"]
    source_data = [make_create_source(base_factory, source=sk) for sk in sources]
    if name:
        source_data.append(make_create_source(base_factory, source="rmi", name=name))

    return OGFieldResourceCreate(
        id=None,
        source_data=source_data,
        constituents=frozenset(),
        repointed_to=None,
        view=None,
        provenance={},
    )


def make_empty_resource(
    *,
    factory: ResourceFactory,
    base_factory: OGFieldBaseFactory,
    sources: list[tuple[OGSISrcKey, bool]] = [],
) -> OGFieldResource:
    """Alias for make_create_resource() kept for readability."""
    return make_resource(
        fact=factory, base_fact=base_factory, empty=True, sources=sources
    )
