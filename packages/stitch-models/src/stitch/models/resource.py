from typing import Sequence
from typing_extensions import Self
from pydantic import BaseModel, Field


class ResourceBase(BaseModel):
    name: str | None = Field(default=None)
    country: str | None = Field(default=None)
    repointed_to: "Resource | None" = Field(default=None)


class Resource(ResourceBase):
    id: int
    source_data: SourceData
    constituents: Sequence[Self]
