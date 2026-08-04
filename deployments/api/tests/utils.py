# pyright: reportAny=false
"""Factory functions for creating test data.

Provides factory functions that return both Pydantic models and dictionaries
for use in tests and HTTP client requests.
"""

from __future__ import annotations

from functools import partial
from typing import Any, TypeVar

from pydantic import BaseModel
from stitch.ogsi.model import (
    CCRSource,
    GemSource,
    LLMSource,
    OGSISrcKey,
    RMISource,
    WoodMacSource,
    OGFieldSource,
    OGFieldResource,
    SourceRecord,
)
from datetime import UTC, datetime

from .factories import OGFieldBaseFactory, ResourceFactory

T = TypeVar("T", bound=BaseModel)


def make_source_record(
    payload: dict[str, Any] | None = None,
    *,
    producer: str = "test-producer",
) -> SourceRecord:
    return SourceRecord(
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        producer=producer,
        payload=payload or {"kind": "fixture"},
    )


def make_source_model(
    *,
    source: OGSISrcKey,
    created_by_id: int,
    source_record: dict[str, Any] | None = None,
    **attrs: Any,
):
    """Build a long-form source header ORM model + its value rows from kwargs.

    Mirrors how the app persists a source record: identity/raw payload on the
    header, each non-null attribute as a typed row in the long values table.
    """
    from stitch.api.db.model import OilGasFieldSourceModel
    from stitch.api.db.model.oil_gas_field_source_value import (
        ATTRIBUTE_NAMES,
        OilGasFieldSourceValueModel,
    )

    if source_record is None:
        record_payload = {"source": source, **attrs}
        source_record = make_source_record(payload=record_payload).model_dump(
            mode="json"
        )

    model = OilGasFieldSourceModel(
        source=source,
        source_record=source_record,
        created_by_id=created_by_id,
        last_updated_by_id=created_by_id,
    )
    model.values = [
        OilGasFieldSourceValueModel.from_attribute(colname, value)
        for colname, value in attrs.items()
        if colname in ATTRIBUTE_NAMES and value is not None and value != ""
    ]
    return model


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
        "source_record": make_source_record({"source": source, "name": src_name}),
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
        case "ccr":
            return CCRSource(**kwargs)


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
    factory: ResourceFactory,
    base_factory: OGFieldBaseFactory,
    sources: list[tuple[OGSISrcKey, bool]] | None = None,
) -> OGFieldResource:
    """Create a minimal Resource payload for creation tests."""
    _mk_src = partial(make_source, fact=base_factory)
    if sources is None:
        sources = [("gem", False)]
    source_data = [_mk_src(managed=mgd, source=sk) for sk, mgd in sources]
    if name:
        src = _mk_src(managed=False, source="rmi")
        src.name = name
        source_data.append(src)

    model = factory.build(
        id=None,
        source_data=source_data,
        constituents=frozenset(),
        repointed_to=None,
        view=None,
        provenance={},
    )
    return model


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
