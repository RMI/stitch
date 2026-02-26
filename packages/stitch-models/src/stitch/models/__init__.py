from collections import defaultdict
from collections.abc import Mapping, MutableMapping, MutableSequence, Sequence
from typing import (
    ClassVar,
    NamedTuple,
    TypeVar,
    Self,
)
from pydantic import BaseModel, Field, ConfigDict

from .types import IdType

__all__ = [
    "Resource",
    "ResourceBase",
    "SourceBase",
    "SourceBaseCollection",
    "MutableSourceBaseCollection",
    "Source",
    "SourceCollection",
    "MutableSourceCollection",
    "SourcePayload",
    "SourceRef",
]


class SourceBase[TSrcKey: str](BaseModel):
    """Base class for `Source` data without id field.

    Used for creational patterns and to handle use cases where identifiers should NOT be present.

    Attributes:
        source: key for identifying the data source
    """

    source: TSrcKey

    # we set `from_attributes=True` to accommodate ORM or other object mappings
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


TSrcBase = TypeVar("TSrcBase", bound=SourceBase[str])
SourceBaseCollection = Sequence[TSrcBase]
MutableSourceBaseCollection = MutableSequence[TSrcBase]


class Source[TId: IdType, TSrcKey: str](SourceBase[TSrcKey]):
    """Canonical source model that has been integrated/stored.

    Attributes:
        id: unique identifier within `source` scope
        source: key for identifying the data source
    """

    id: TId


TId = TypeVar("TId", bound=IdType)
TSrc = TypeVar("TSrc", bound=Source[IdType, str])
SourceCollection = Mapping[TId, TSrc]
MutableSourceCollection = MutableMapping[TId, TSrc]


class SourcePayload(BaseModel):
    """Base for domain-specific source payload containers.

    Subclass and declare attributes typed as SourceCollection[TId, TSrc].
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class SourceRef[TId: IdType, TSrcKey: str](NamedTuple):
    source: TSrcKey
    id: TId


class ResourceBase[TPayload: SourcePayload](BaseModel):
    """Base class for `Resource` objects without identifiers.

    Used for creational patterns or other use cases where identifiers should NOT be present (e.g. ETL).

    Attributes:
        source_data: instance of `SourcePayload` subclass (note: be sure to use `SourceBaseCollection` variants here)
    """

    source_data: TPayload


class Resource[TPayload: SourcePayload, TResId: IdType](ResourceBase[TPayload]):
    """Canonical `Resource` model.

    Identifiers are required for merge, split, and repointing operations in most production contexts.

    Examples:
    ```
    class MyResource(Resource[MyPayload, int]):
        pass
    ```

    Attributes:
        id: unique resource identifier
        repointed_to: the new "parent" resource to which *this* resource points (result of merging)
        provenance: maps resource IDs to sequences of SourceRefs for data lineage introspection
    """

    id: TResId
    repointed_to: Self | None = Field(default=None)
    provenance: Mapping[TResId, Sequence[SourceRef[IdType, str]]] = Field(
        default_factory=lambda: defaultdict(list)
    )
