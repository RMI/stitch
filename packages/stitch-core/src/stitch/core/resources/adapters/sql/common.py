from typing import Protocol


class HasId(Protocol):
    id: int


def extract_id(entity: HasId | int) -> int:
    if hasattr(entity, "id"):
        return entity.id
    return entity
