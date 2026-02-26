from collections import defaultdict
from collections.abc import Mapping, MutableMapping, MutableSequence, Sequence
from typing import (
    ClassVar,
    Self,
    TypeVar,
)

from pydantic import BaseModel, ConfigDict, Field

from .types import IdType, Provenance, SourceRef

__all__ = [
    "ManagedResource",
    "Resource",
    "Source",
    "SourcePayload",
]


class Source[TSrcKey: str](BaseModel):
    """Base class for dependent, canonical `Source` data declarations.

    Used for creational patterns and to handle use cases where identifiers should NOT be present.

    Attributes:
        source: key for identifying the data source
    """

    source: TSrcKey

    # we set `from_attributes=True` to accommodate ORM or other object mappings
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


Ts = TypeVar("Ts", bound=str)
Tid = TypeVar("Tid", bound=IdType)
SourceSequence = Sequence[Source[Ts]]
MutableSourceSequence = MutableSequence[Source[Ts]]
SourceMapping = Mapping[SourceRef[Tid, Ts], Source[Ts]]
MutableSourceMapping = MutableMapping[SourceRef[Tid, Ts], Source[Ts]]


class SourcePayload(BaseModel):
    """Base for domain-specific source payload containers.

    Subclass and declare attributes typed as SourceCollection[TId, TSrc].
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class Resource[TPayload: SourcePayload](BaseModel):
    """Base class for `Resource` objects without identifiers.

    Used for creational patterns or other use cases where identifiers should NOT be present (e.g. ETL).

    Attributes:
        source_data: instance of `SourcePayload` subclass (note: be sure to use `SourceBaseCollection` variants here)
    """

    source_data: TPayload
    repointed_to: Self | None = Field(default=None)


class ManagedResource[TResId: IdType, TSrcId: IdType, TSrcKey: str, TPl: SourcePayload](
    Resource[TPl]
):
    id: TResId
    provenance: Provenance[TResId, TSrcId, TSrcKey] = Field(
        default_factory=lambda: defaultdict(list)
    )
