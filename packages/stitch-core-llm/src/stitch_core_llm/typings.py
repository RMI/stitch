from collections.abc import Iterable, Collection
from pydantic import BaseModel
from typing import Protocol


class AISuggestable[T: BaseModel, S: BaseModel](Protocol):
    @property
    def data(self) -> T: ...

    @property
    def source_data(self) -> Iterable[S]: ...

    @property
    def suggestable_fields(self) -> Collection[str]: ...
