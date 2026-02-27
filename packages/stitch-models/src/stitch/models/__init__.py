from collections.abc import Mapping, Sequence
from typing import (
    ClassVar,
    NamedTuple,
)

from pydantic import BaseModel, ConfigDict, Field

from .types import IdType

__all__ = [
    "Resource",
    "Source",
    "SourcePayload",
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
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class SourcePayload(BaseModel):
    """Base for domain-specific source payload containers.

    Subclass and declare attributes typed as SourceCollection[TId, TSrc].
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class SourceRef[TId: IdType, TKey: str](NamedTuple):
    id: TId
    source: TKey


class Resource[
    TResId: IdType,
    TSrcId: IdType,
    TSrcKey: str,
    TPayload: SourcePayload,
](BaseModel):
    id: TResId | None = None
    source_data: TPayload
    repointed_to: TResId | None = Field(default=None)
    provenance: Mapping[TResId, Sequence[SourceRef[TSrcId, TSrcKey]]] = Field(
        default_factory=dict
    )
