from collections.abc import Sequence
from typing import (
    ClassVar,
    NamedTuple,
    Self,
)

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .types import IdType

__all__ = [
    "Resource",
    "Source",
    "SourcePayload",
    "SourceRefTuple",
]


class Source[TId: IdType, TSrcKey: str](BaseModel):
    """Base class for dependent, canonical `Source` data declarations.

    Used for creational patterns and to handle use cases where identifiers should NOT be present.

    Attributes:
        source: key for identifying the data source
    """

    id: TId | None = None
    source: TSrcKey

    # we set `from_attributes=True` to accommodate ORM or other object mappings
    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True, extra="ignore"
    )


class SourcePayload(BaseModel):
    """Base for domain-specific source payload containers.

    Subclass and declare attributes that hold collections (for example, mappings)
    of :class:`Source` instances keyed and structured as appropriate for your domain.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class SourceRefTuple[TId: IdType, TKey: str](NamedTuple):
    id: TId
    source: TKey


class Resource[TResId: IdType, TSrc: Source](BaseModel):
    id: TResId | None = None
    source_data: Sequence[TSrc] = Field(default_factory=lambda: [])
    repointed_to: TResId | None = Field(default=None)
    constituents: frozenset[TResId] = Field(default_factory=frozenset)

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def _no_self_reference(self) -> Self:
        if self.id is not None:
            if self.id in self.constituents:
                raise ValueError("A resource cannot be a constituent of itself")
            if self.repointed_to == self.id:
                raise ValueError("A resource cannot be repointed to itself")
        return self


class Resource_[
    TResId: IdType,
    TPayload: SourcePayload,
](BaseModel):
    id: TResId | None = None
    source_data: TPayload
    repointed_to: TResId | None = Field(default=None)
    constituents: frozenset[TResId] = Field(default_factory=frozenset)

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def _no_self_reference(self) -> Self:
        if self.id is not None:
            if self.id in self.constituents:
                raise ValueError("A resource cannot be a constituent of itself")
            if self.repointed_to == self.id:
                raise ValueError("A resource cannot be repointed to itself")
        return self
