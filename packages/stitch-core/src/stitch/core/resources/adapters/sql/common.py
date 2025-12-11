from typing import Protocol


class HasId(Protocol):
    @property
    def id(self) -> int: ...


def extract_id(entity: HasId | int) -> int:
    if isinstance(entity, int):
        return entity
    return entity.id
