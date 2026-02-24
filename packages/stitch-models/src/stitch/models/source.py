from typing import TypeVar, Mapping, NamedTuple, MutableMapping
from pydantic import BaseModel, ConfigDict

from .types import IdType


class SourceBase[TId: IdType, TSrcKey: str](BaseModel):
    id: TId
    source: TSrcKey

    model_config = ConfigDict(from_attributes=True)


TId = TypeVar("TId", bound=IdType)
TSrc = TypeVar("TSrc", bound=SourceBase)
SourceCollection = Mapping[TId, TSrc]
MutableSourceCollection = MutableMapping[TId, TSrc]


class SourcePayload(BaseModel):
    """Base for domain-specific source payload containers.

    Subclass and declare attributes typed as SourceCollection[TId, TSrc].
    """

    model_config = ConfigDict(from_attributes=True)


class SourceRef[TId: IdType, TSrcKey: str](NamedTuple):
    source: TSrcKey
    id: TId
