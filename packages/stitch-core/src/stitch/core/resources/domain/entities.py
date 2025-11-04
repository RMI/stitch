from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Required, TypedDict


@dataclass(frozen=True, kw_only=True)
class MembershipEntity:
    id: int
    resource_id: int
    dataset: str
    source_pk: str
    created_by: str | None = None
    status: str | None = None
    created: datetime


class MembershipEntityData(TypedDict, total=False):
    resource_id: Required[int]
    dataset: Required[str]
    source_pk: Required[str]
    created_by: str | None = None
    status: str | None = None


@dataclass(frozen=True, kw_only=True)
class ResourceEntity:
    id: int
    repointed_id: int | None = None
    # aggregated resources will not have
    # a dataset an sourcepk
    dataset: str | None = None
    source_pk: str | None = None

    # Canonical projection
    name: str | None = None
    country_iso3: str | None = None
    operator: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    created: datetime

    def __eq__(self, other) -> bool:
        if not isinstance(other, ResourceEntity):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash((self.id, self.dataset, self.source_pk))


class ResourceEntityData(TypedDict, total=False):
    repointed_id: int | None = None
    dataset: str | None = None
    source_pk: str | None = None
    name: str | None = None
    country_iso3: str | None = None
    operator: str | None = None
    latitude: float | None = None
    longitude: float | None = None
