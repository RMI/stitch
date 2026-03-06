from collections.abc import Sequence
from datetime import datetime
from typing import (
    Self,
)
from pydantic import BaseModel, EmailStr, Field

from stitch.ogsi.model import OGFieldSource


class Timestamped(BaseModel):
    created: datetime = Field(default_factory=datetime.now)
    updated: datetime = Field(default_factory=datetime.now)


# The sources will come in and be initially stored in a raw table.
# That raw table will be an append-only table.
# We'll translate that data into one of the below structures, so each source will have a `UUID` or similar that
# references their id in the "raw" table.
# When pulling into the internal "sources" table, each will get a new unique id which is what the memberships will reference


class ResourceBase(BaseModel):
    name: str | None = Field(default=None)
    country: str | None = Field(default=None)
    repointed_to: Self | None = Field(default=None)


class Resource(ResourceBase, Timestamped):
    id: int
    source_data: Sequence[OGFieldSource] = Field(default_factory=lambda: [])
    constituents: Sequence[Self] = Field(default_factory=lambda: [])


class User(BaseModel):
    id: int = Field(...)
    sub: str = Field(...)
    role: str | None = None
    email: EmailStr
    name: str
