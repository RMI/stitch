"""Factory functions for creating test data.

Provides factory functions that return both Pydantic models and dictionaries
for use in tests and HTTP client requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from stitch.api.entities import Resource

T = TypeVar("T", bound=BaseModel)


@dataclass
class FactoryResult(Generic[T]):
    """Holds both model and dict representations of test data."""

    model: T

    @property
    def data(self) -> dict[str, Any]:
        """Return dict representation via model_dump()."""
        return self.model.model_dump(mode="json")


def make_create_resource(
    *,
    name: str | None = None,
) -> FactoryResult[Resource]:
    """Create a minimal Resource payload for creation tests."""
    return FactoryResult(model=Resource(id=0, name=name))


def make_empty_resource(
    *,
    name: str | None = None,
) -> FactoryResult[Resource]:
    """Alias for make_create_resource() kept for readability."""
    return make_create_resource(name=name)
