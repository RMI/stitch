"""Factory functions for creating test data.

Provides factory functions that return both Pydantic models and dictionaries
for use in tests and HTTP client requests.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from stitch.api.entities import (
    CreateResource,
    CreateResourceSourceData,
    GemData,
    RMIManualData,
    WMData,
)

T = TypeVar("T", bound=BaseModel)


@dataclass
class FactoryResult(Generic[T]):
    """Holds both model and dict representations of test data."""

    model: T

    @property
    def data(self) -> dict[str, Any]:
        """Return dict representation via model_dump()."""
        return self.model.model_dump()


# Static defaults for each source type (no id - these are for creation)
GEM_DEFAULTS: dict[str, Any] = {
    "name": "Default GEM Field",
    "latitude": 45.0,
    "longitude": -120.0,
    "country": "USA",
}

WM_DEFAULTS: dict[str, Any] = {
    "name": "Default WM Field",
    "country": "USA",
}

RMI_DEFAULTS: dict[str, Any] = {
    "name": "Default RMI",
    "country": "USA",
    "latitude": 40.0,
    "longitude": -100.0,
}


def make_gem_data(
    name: str = GEM_DEFAULTS["name"],
    latitude: float = GEM_DEFAULTS["latitude"],
    longitude: float = GEM_DEFAULTS["longitude"],
    country: str = GEM_DEFAULTS["country"],
    **kwargs: Any,
) -> FactoryResult[GemData]:
    """Create a GemData with both model and dict representations."""
    return FactoryResult(
        model=GemData(
            name=name, latitude=latitude, longitude=longitude, country=country, **kwargs
        )
    )


def make_wm_data(
    name: str = WM_DEFAULTS["name"],
    country: str = WM_DEFAULTS["country"],
    **kwargs: Any,
) -> FactoryResult[WMData]:
    """Create a WMData with both model and dict representations."""
    return FactoryResult(model=WMData(name=name, country=country, **kwargs))


def make_rmi_data(
    name: str = RMI_DEFAULTS["name"],
    country: str = RMI_DEFAULTS["country"],
    latitude: float = RMI_DEFAULTS["latitude"],
    longitude: float = RMI_DEFAULTS["longitude"],
    **kwargs: Any,
) -> FactoryResult[RMIManualData]:
    """Create an RMIManualData with both model and dict representations."""
    return FactoryResult(
        model=RMIManualData(
            name=name,
            country=country,
            latitude=latitude,
            longitude=longitude,
            **kwargs,
        )
    )


def make_source_data(
    gem: Sequence[GemData | int] | None = None,
    wm: Sequence[WMData | int] | None = None,
    rmi: Sequence[RMIManualData | int] | None = None,
) -> FactoryResult[CreateResourceSourceData]:
    """Create CreateResourceSourceData with both model and dict representations.

    Args:
        gem: List of GemData models or existing source IDs
        wm: List of WMData models or existing source IDs
        rmi: List of RMIManualData models or existing source IDs

    Returns:
        FactoryResult with model and data (dict) attributes
    """
    return FactoryResult(
        model=CreateResourceSourceData(
            gem=list(gem or []),
            wm=list(wm or []),
            rmi=list(rmi or []),
        )
    )


def make_create_resource(
    name: str | None = "Test Resource",
    country: str | None = "USA",
    source_data: CreateResourceSourceData
    | FactoryResult[CreateResourceSourceData]
    | None = None,
) -> FactoryResult[CreateResource]:
    """Create a CreateResource with both model and dict representations.

    Args:
        name: Resource name (optional)
        country: Country code (optional)
        source_data: Either a CreateResourceSourceData model, a FactoryResult,
                     or None for empty source data

    Returns:
        FactoryResult with model and data (dict) attributes
    """
    if source_data is None:
        sd_model = None
    elif isinstance(source_data, FactoryResult):
        sd_model = source_data.model
    else:
        sd_model = source_data

    return FactoryResult(
        model=CreateResource(name=name, country=country, source_data=sd_model)
    )


# Convenience factory functions for common test scenarios


def make_empty_resource(
    name: str | None = "Empty Resource",
    country: str | None = "USA",
) -> FactoryResult[CreateResource]:
    """Create a resource with no source data."""
    return make_create_resource(name=name, country=country, source_data=None)


def make_resource_with_new_sources(
    gem: GemData | Sequence[GemData] | None = None,
    wm: WMData | Sequence[WMData] | None = None,
    rmi: RMIManualData | Sequence[RMIManualData] | None = None,
    name: str | None = "Resource with Sources",
    country: str | None = "USA",
) -> FactoryResult[CreateResource]:
    """Create a resource with new source data only (no existing IDs)."""

    def to_list(item: Any | Sequence[Any] | None) -> list[Any]:
        if item is None:
            return []
        if isinstance(item, (list, tuple)):
            return list(item)
        return [item]

    source_data = make_source_data(
        gem=to_list(gem),
        wm=to_list(wm),
        rmi=to_list(rmi),
    )
    return make_create_resource(name=name, country=country, source_data=source_data)


def make_resource_with_existing_ids(
    gem_ids: Sequence[int] | None = None,
    wm_ids: Sequence[int] | None = None,
    rmi_ids: Sequence[int] | None = None,
    name: str | None = "Resource with Existing Sources",
    country: str | None = "USA",
) -> FactoryResult[CreateResource]:
    """Create a resource referencing existing source IDs only."""
    source_data = make_source_data(
        gem=list(gem_ids or []),
        wm=list(wm_ids or []),
        rmi=list(rmi_ids or []),
    )
    return make_create_resource(name=name, country=country, source_data=source_data)


def make_resource_with_mixed_sources(
    new_gem: GemData | Sequence[GemData] | None = None,
    existing_gem_ids: Sequence[int] | None = None,
    new_wm: WMData | Sequence[WMData] | None = None,
    existing_wm_ids: Sequence[int] | None = None,
    new_rmi: RMIManualData | Sequence[RMIManualData] | None = None,
    existing_rmi_ids: Sequence[int] | None = None,
    name: str | None = "Resource with Mixed Sources",
    country: str | None = "USA",
) -> FactoryResult[CreateResource]:
    """Create a resource with a mix of new source data and existing source IDs."""

    def to_list(item: Any | Sequence[Any] | None) -> list[Any]:
        if item is None:
            return []
        if isinstance(item, (list, tuple)):
            return list(item)
        return [item]

    gem_items: list[GemData | int] = to_list(new_gem) + list(existing_gem_ids or [])
    wm_items: list[WMData | int] = to_list(new_wm) + list(existing_wm_ids or [])
    rmi_items: list[RMIManualData | int] = to_list(new_rmi) + list(
        existing_rmi_ids or []
    )

    source_data = make_source_data(gem=gem_items, wm=wm_items, rmi=rmi_items)
    return make_create_resource(name=name, country=country, source_data=source_data)
